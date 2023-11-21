import rclpy
from rclpy.node import Node
from std_srvs.srv import Empty
from visualization_msgs.msg import MarkerArray
from rclpy.qos import QoSProfile, QoSDurabilityPolicy
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
import tf2_ros
from tf2_ros.buffer import Buffer
from tf2_ros.transform_listener import TransformListener
from tf2_ros.static_transform_broadcaster import StaticTransformBroadcaster
from geometry_msgs.msg import TransformStamped, Quaternion
from trajectory_interfaces.srv import Target, TargetScanRequest


class ControlNode(Node):
    def __init__(self):
        super().__init__("control")
        # Broadcast a camera frame
        self.camera_broadcaster = StaticTransformBroadcaster(self)
        self._cam_hand_tf = TransformStamped()
        self._cam_hand_tf.header.stamp = self.get_clock().now().to_msg()
        self._cam_hand_tf.header.frame_id = "panda_hand"
        self._cam_hand_tf.child_frame_id = "camera_link"
        self._cam_hand_tf.transform.translation.x = 0.05
        self._cam_hand_tf.transform.translation.z = 0.065
        self._cam_hand_tf.transform.rotation = Quaternion(
            x=0.707, y=0.0, z=0.707, w=0.0
        )
        self.camera_broadcaster.sendTransform(self._cam_hand_tf)  # publish transform

        # Callback group
        self._cbgrp = ReentrantCallbackGroup()
        self.loop_cbgrp = MutuallyExclusiveCallbackGroup()
        self.tf_cbgrp = MutuallyExclusiveCallbackGroup()

        # clients and publishers
        self._input_client = self.create_client(
            Empty, "input", callback_group=self._cbgrp
        )
        self._vision_client = self.create_client(
            Empty, "coordinates", callback_group=self._cbgrp
        )
        self._targets_client = self.create_client(
            TargetScanRequest, "target_scan", callback_group=self._cbgrp
        )
        self._gun_client = self.create_client(
            Empty, "gun_scan", callback_group=self._cbgrp
        )

        # # wait for services to become available
        # while not self._input_client.wait_for_service(timeout_sec=1.0):
        #     self.get_logger().info('service not available, waiting again...')

        # while not self._vision_client.wait_for_service(timeout_sec=1.0):
        #     self.get_logger().info('service not available, waiting again...')

        while not self._gun_client.wait_for_service(timeout_sec=1.0):
            self.get_logger().info("service not available, waiting again...")

        # main loop timer
        self._loop_timer = self.create_timer(
            0.01, self.loop_cb, callback_group=self.loop_cbgrp
        )
        self._tf_timer = self.create_timer(
            0.01, self.tf_cb, callback_group=self.tf_cbgrp
        )

        # variables
        self._markers = None  # store the MarkerArray
        self.t1_x = None
        self.t1_y = None
        self.t1_z = None
        self.t1_ox = None
        self.t1_oy = None
        self.t1_ow = None
        self.t1_oz = None

        # TF listener
        self.buffer = Buffer()
        self.listener = TransformListener(self.buffer, self)

        # run once
        self._run = False

    async def loop_cb(self):
        """Main loop."""

        if not self._run:
            self._run = True
            # RUN ONCE!
            # scan targets
            await self.scan_targets()
            ## scan guns
            # self._gun_scan_future = await self._gun_client.call_async(Empty.Request())
            # self.get_logger().info(f"Tag 1 coordinates: ({self.t1_x},{self.t1_y},{self.t1_z})")

            # wait for user input
            # shoot
            return

    def tf_cb(self):
        """Listens to tf data to track April Tags."""
        # TF listener
        try:
            # get the latest transform between left and right
            # (rclpy.time.Time() means get the latest information)
            tag_1 = self.buffer.lookup_transform(
                "camera_link", "tag36h11:1", rclpy.time.Time()
            )
            self.t1_x = tag_1.transform.translation.x
            self.t1_y = tag_1.transform.translation.y
            self.t1_z = tag_1.transform.translation.z
            self.t1_ox = tag_1.transform.rotation.x
            self.t1_oy = tag_1.transform.rotation.y
            self.t1_ow = tag_1.transform.rotation.w
            self.t1_oz = tag_1.transform.rotation.z
        except tf2_ros.LookupException as e:
            # the frames don't exist yet
            self.get_logger().debug(f"Lookup exception: {e}")
        except tf2_ros.ConnectivityException as e:
            # the tf tree has a disconnection
            self.get_logger().debug(f"Connectivity exception: {e}")
        except tf2_ros.ExtrapolationException as e:
            # the times are two far apart to extrapolate
            self.get_logger().debug(f"Extrapolation exception: {e}")

    def publish_markers(self):
        """Pusblishes YOLO detections as Markers to visualize them in Rviz."""
        self._marker_pub.publish(self._markers)

        return

    async def scan_targets(self):
        """Moves the robot to scanning positions and requests for detections."""
        # move robot to scan position
        self.get_logger().info("position 1")
        response = await self._targets_client.call_async(TargetScanRequest.Request())
        # scan pins
        self.get_logger().info("requesting camera scan...")
        await self._vision_client.call_async(Empty.Request())
        self.get_logger().info("camera scan complete")
        count = 2
        while response.more_scans:
            # move robot to scan position
            self.get_logger().info(f"position {count}")
            response = await self._targets_client.call_async(
                TargetScanRequest.Request()
            )
            count += 1
            # scan pins
            self.get_logger().info("requesting camera scan...")
            await self._vision_client.call_async(Empty.Request())
            self.get_logger().info("camera scan complete")
        return


def main():
    rclpy.init()
    node = ControlNode()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    executor.spin()


if __name__ == "__main__":
    main()