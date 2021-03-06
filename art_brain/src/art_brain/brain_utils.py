import matplotlib.path as mplPath
import numpy as np
import rospy
import actionlib
from art_msgs.msg import pickplaceAction, ObjInstance
import copy
from std_srvs.srv import Empty, Trigger
from geometry_msgs.msg import Pose


class ArtBrainUtils(object):

    @staticmethod
    def get_pick_obj(instruction, objects):
        for obj in objects:
            if obj.object_id == instruction.object:
                obj_ret = copy.deepcopy(obj)
                return obj_ret
        else:
            return None

    @staticmethod
    def get_pick_obj_from_feeder(instruction):
        obj = ObjInstance()
        obj.object_id = None
        obj.object_type = instruction.object
        obj.pose = Pose()
        return obj

    @staticmethod
    def get_pick_obj_from_polygon(instruction, objects):
        pick_polygon = []
        pol = None
        obj_ret = None

        # TODO check frame_id and transform to table frame?
        for point in instruction.pick_polygon.polygon.points:
            pick_polygon.append([point.x, point.y])
        pick_polygon.append([0, 0])

        if len(pick_polygon) > 0:
            pol = mplPath.Path(np.array(pick_polygon), closed=True)

        # shuffle the array to not get the same object each time
        # random.shuffle(self.objects.instances)

        for obj in objects.instances:

            if pol is None:

                # if no pick polygon is specified - let's take the first
                # object of that type
                if obj.object_type == instruction.object:
                    obj_ret = copy.deepcopy(obj)
                    break

            else:

                # test if some object is in polygon and take the first one
                if pol.contains_point([obj.pose.position.x, obj.pose.position.y]):
                    obj_ret = copy.deepcopy(obj)
                    print('Selected object: ' + obj.object_id)
                    break

        else:
            if pol is not None:
                print('No object in the specified polygon')
                print pol
            return None
        return obj_ret

    @staticmethod
    def get_place_pose(instruction):

        if instruction.spec == instruction.MANIP_ID:
            pose = instruction.place_pose
        elif instruction.spec == instruction.MANIP_TYPE:
            # pose = None
            pose = instruction.place_pose
            # TODO: how to get free position inside polygon? some perception
            # node?
        else:
            return None
        return pose

    @staticmethod
    def distance_2d(pose1, pose2):
        a = np.array((pose1.position.x, pose1.position.y))
        b = np.array((pose2.position.x, pose2.position.y))
        return np.linalg.norm(a - b)


class ArtGripper(object):

    GRIPPER_LEFT = 0
    GRIPPER_RIGHT = 1
    GRIPPER_BOTH = 2

    def __init__(self, name):
        self.name = name
        self.pp_client_name = "/art/pr2/" + name + "/pp"
        self.pp_client = actionlib.SimpleActionClient(
            self.pp_client_name, pickplaceAction)
        self.holding_object = None
        self.group_name = name
        self.interaction_on_client = rospy.ServiceProxy(
            "/art/pr2/" + name + "/interaction/on", Empty)
        self.interaction_off_client = rospy.ServiceProxy(
            "/art/pr2/" + name + "/interaction/off", Empty)
        self.get_ready_client = rospy.ServiceProxy(
            "/art/pr2/" + name + "/get_ready", Trigger)
        self.move_to_user_client = rospy.ServiceProxy(
            "/art/pr2/" + name + "/move_to_user", Trigger)


class ErrorMsgs(object):

    MISSING_OBJECT = ""
