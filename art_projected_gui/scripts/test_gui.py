#! /usr/bin/env python
import rospy
from geometry_msgs.msg import PoseStamped,  Quaternion
from art_msgs.msg import InstancesArray, ObjInstance
import tf
from math import pi


def isclose(a, b, rel_tol=1e-09, abs_tol=0.0):

    return abs(a-b) <= max(rel_tol * max(abs(a), abs(b)), abs_tol)


def yaw2orientation(yaw):

    quaternion = tf.transformations.quaternion_from_euler(0, 0, yaw/360.0*2*pi)
    orientation = Quaternion()

    orientation.x = quaternion[0]
    orientation.y = quaternion[1]
    orientation.z = quaternion[2]
    orientation.w = quaternion[3]

    return orientation


def main():

    pub = rospy.Publisher("/art/object_detector/object_filtered", InstancesArray, queue_size=10)
    pub_point_left = rospy.Publisher("/art/user/pointing_left", PoseStamped, queue_size=10)
    pub_point_right = rospy.Publisher("/art/user/pointing_right", PoseStamped, queue_size=10)

    arr = InstancesArray()
    arr.header.frame_id = "marker"
    arr.header.stamp = rospy.Time.now()

    obj = ObjInstance()
    obj.object_id = "my_object"
    obj.object_type = "profile_20_60"
    obj.pose.position.x = 0.5
    obj.pose.position.y = 0.5
    obj.pose.position.z = 0.0
    obj.pose.orientation = yaw2orientation(0)

    arr.instances.append(obj)

    obj2 = ObjInstance()
    obj2.object_id = "another_object"
    obj2.object_type = "profile_20_60"
    obj2.pose.position.x = 0.7
    obj2.pose.position.y = 0.2
    obj2.pose.position.z = 0.0
    obj2.pose.orientation = yaw2orientation(45/2)

    arr.instances.append(obj2)

    obj3 = ObjInstance()
    obj3.object_id = "even_another_object"
    obj3.object_type = "profile_20_60"
    obj3.pose.position.x = 0.9
    obj3.pose.position.y = 0.3
    obj3.pose.position.z = 0.0
    obj3.pose.orientation = yaw2orientation(45)

    arr.instances.append(obj3)

    arr.new_objects.append(obj.object_id)
    arr.new_objects.append(obj2.object_id)
    arr.new_objects.append(obj3.object_id)

    ps = PoseStamped()
    ps.header.stamp = rospy.Time.now()
    ps.header.frame_id = "marker"
    ps.pose.position.x = 0.0
    ps.pose.position.y = 0.5
    ps.pose.position.z = 0
    ps.pose.orientation.x = 0.0
    ps.pose.orientation.y = 0.0
    ps.pose.orientation.z = 0.0
    ps.pose.orientation.w = 1.0

    psr = PoseStamped()
    psr.header.stamp = rospy.Time.now()
    psr.header.frame_id = "marker"
    psr.pose.position.x = 0.0
    psr.pose.position.y = 0.3
    psr.pose.position.z = 0
    psr.pose.orientation.x = 0.0
    psr.pose.orientation.y = 0.0
    psr.pose.orientation.z = 0.0
    psr.pose.orientation.w = 1.0

    noise = 0.0001

    rospy.sleep(2.0)
    pub.publish(arr)
    rospy.sleep(1.0)
    arr.new_objects = []

    while(not rospy.is_shutdown()):
        pub.publish(arr)
        rospy.sleep(1.0)

    while(not rospy.is_shutdown()):

        if psr.pose.position.x < 0.8:

            psr.pose.position.x += 0.003

        else:

            psr.pose.position.x = 0
            psr.pose.position.y = 0.3

        pub_point_right.publish(psr)

        if ps.pose.position.x < 0.8:

            ps.pose.position.x += 0.002

        else:

            ps.pose.position.x = 0
            ps.pose.position.y = 0.5

        if isclose(ps.pose.position.x, 0.5):

            for i in range(0, 300):

                pub.publish(arr)
                pub_point_left.publish(ps)
                rospy.sleep(0.01)

        if isclose(ps.pose.position.x, 0.6):

            for i in range(0, 300):

                pub.publish(arr)
                pub_point_left.publish(ps)
                rospy.sleep(0.01)

        pub.publish(arr)
        pub_point_left.publish(ps)

        rospy.sleep(0.01)

if __name__ == '__main__':
    try:
        rospy.init_node('gui_test_node')
        main()
    except rospy.ROSInterruptException:
        print "program interrupted before completion"
