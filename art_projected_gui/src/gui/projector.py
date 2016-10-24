#!/usr/bin/env python

from PyQt4 import QtGui, QtCore
import rospkg
from cv_bridge import CvBridge, CvBridgeError
from sensor_msgs.msg import CompressedImage,  Image,  CameraInfo
import rospy
import cv2
import numpy as np
from std_msgs.msg import Bool
from std_srvs.srv import Empty, EmptyResponse
import message_filters
from image_geometry import PinholeCameraModel
from geometry_msgs.msg import PointStamped,  Pose,  PoseArray
import tf

# TODO create ProjectorROS (to separate QT / ROS stuff)
# warpovani obrazu pro kazdy z projektoru
# podle vysky v pointcloudu / pozice projektoru se vymaskuji mista kde je neco vyssiho - aby se promitalo jen na plochu stolu ????

class Projector(QtGui.QWidget):

    def __init__(self, proj_id, screen,  camera_image_topic, camera_depth_topic,  camera_info_topic,  h_matrix,  world_frame="marker"):

        super(Projector, self).__init__()

        rospy.loginfo("Projector '" + proj_id + "', on screen " + str(screen) )

        self.calibrated = False
        self.h_matrix = h_matrix
        if self.h_matrix is not None:
            self.calibrated = True

        self.proj_id = proj_id
        self.world_frame = world_frame

        img_path = rospkg.RosPack().get_path('art_projected_gui') + '/imgs'
        self.checkerboard_img = QtGui.QPixmap(img_path + "/pattern.png")
        self.calibrating = False
        self.camera_image_topic = camera_image_topic
        self.camera_depth_topic = camera_depth_topic
        self.camera_info_topic = camera_info_topic

        desktop = QtGui.QDesktopWidget()
        geometry = desktop.screenGeometry(screen)
        self.move(geometry.left(), geometry.top())
        self.resize(geometry.width(), geometry.height())

        self.tfl = None
        self.bridge = CvBridge()

        self.setAutoFillBackground(True)
        p = self.palette()
        p.setColor(self.backgroundRole(), QtCore.Qt.black)
        #self.setPalette(p)

        self.pix_label = QtGui.QLabel(self)
        self.pix_label.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)
        #self.pix_label.setScaledContents(True)
        self.pix_label.resize(self.size())

        QtCore.QObject.connect(self, QtCore.SIGNAL('scene'), self.scene_evt)
        self.scene_sub = rospy.Subscriber("/art/interface/projected_gui/scene",  CompressedImage,  self.scene_cb,  queue_size=1)

        self.calibrated_pub = rospy.Publisher("/art/interface/projected_gui/projector/" + proj_id + "/calibrated",  Bool,  queue_size=1,  latch=True)
        self.calibrated_pub.publish(self.calibrated)

        self.srv_calibrate = rospy.Service("/art/interface/projected_gui/projector/" + proj_id + "/calibrate", Empty, self.calibrate_srv_cb)

        QtCore.QObject.connect(self, QtCore.SIGNAL('show_chessboard'), self.show_chessboard_evt)

        self.showFullScreen()

    def calibrate(self,  image,  info,  depth):

        model = PinholeCameraModel()
        model.fromCameraInfo(info)

        try:
              cv_img = self.bridge.imgmsg_to_cv2(image, "bgr8")
        except CvBridgeError as e:
            print(e)
            return False

        try:
              cv_depth = self.bridge.imgmsg_to_cv2(depth)
        except CvBridgeError as e:
          print(e)
          return False

        cv_depth = cv2.medianBlur(cv_depth, 5)
        cv_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

        ret, corners = cv2.findChessboardCorners(cv_img, (9,6), None, flags=cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_FILTER_QUADS | cv2.CALIB_CB_NORMALIZE_IMAGE)

        if ret == False:

            rospy.logerr("Could not find chessboard corners")
            return False

        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.001)
        cv2.cornerSubPix(cv_img,corners,(11,11),(-1,-1),criteria)
        corners = corners.reshape(1,-1,2)[0]

        #print "corners"
        #print corners

        points = []
        ppoints = []

        ppp = PoseArray()
        ppp.header.stamp = rospy.Time.now()
        ppp.header.frame_id = self.world_frame

        for c in corners:

              pt = list(model.projectPixelTo3dRay((c[0], c[1])))
              pt[:] = [x/pt[2] for x in pt]

              # depth image is noisy - let's make mean of few pixels
              da = []
              for x in range(int(c[0]) - 2, int(c[0]) + 3):
                  for y in range(int(c[1]) - 2, int(c[1]) + 3):
                      da.append(cv_depth[y, x]/1000.0)

              d = np.mean(da)
              pt[:] = [x*d for x in pt]

              ps = PointStamped()
              ps.header.stamp = rospy.Time(0)
              ps.header.frame_id = image.header.frame_id
              ps.point.x = pt[0]
              ps.point.y = pt[1]
              ps.point.z = pt[2]

              # transform 3D point from camera into the world coordinates
              try:
                  ps = self.tfl.transformPoint(self.world_frame, ps)
              except (tf.LookupException, tf.ConnectivityException, tf.ExtrapolationException):
                  rospy.logerr("can't get transform")
                  return False

              pp = Pose()
              pp.position.x = ps.point.x
              pp.position.y = ps.point.y
              pp.position.z = ps.point.z
              pp.orientation.x = 0
              pp.orientation.y = 0
              pp.orientation.z = 0
              pp.orientation.w = 1.0

              ppp.poses.append(pp)

              # store x,y -> here we assume that points are 2D (on tabletop)
              points.append([1280*ps.point.x, 1280*ps.point.y])

        # generate requested table coordinates
        # TODO fix it ;-)
        for y in range(0,6):
              for x in range(0,9):

                    px = 1.2 - (x/8.0*1.2)
                    py = y/5.0*0.75

                    ppoints.append([1280*px, 1280*py])

#        print
#        print "points"
#        print points
#        print
#
#        print "ppoints"
#        print ppoints
#        print

        h, status = cv2.findHomography(np.array(points), np.array(ppoints), cv2.LMEDS)

        self.h_matrix = np.matrix(h)
        #self.h_matrix = np.matrix([[1,  0,  0], [0,  1,  0], [0,  0, 1.0]])

        # store homography matrix to parameter server
        s = str(self.h_matrix.tolist())
        rospy.set_param("~calibration_matrix",  s)
        print s

        return True

    def shutdown_ts(self):

        self.timeout_timer.shutdown()

        # TODO is this correct way how to shut it down?
        for sub in self.subs:
            sub.sub.unregister()
        self.ts = None

    def sync_cb(self,  image,  cam_info,  depth):

        self.timeout_timer.shutdown()
        self.timeout_timer = rospy.Timer(rospy.Duration(3.0),  self.timeout_timer_cb,  oneshot=True)

        if self.calibrate(image,  cam_info,  depth):

            self.calibrated = True
            self.tfl = None
            rospy.loginfo('Calibrated')

        else:

            self.calibration_attempts += 1

            if self.calibration_attempts < 10:
                return

            rospy.logerr('Calibration failed')
            self.calibrated = False

        self.shutdown_ts()
        self.calibrated_pub.publish(self.calibrated)
        self.calibrating = False

    def show_chessboard_evt(self):

        rat = 1.0 # TODO make checkerboard smaller and smaller if it cannot be detected?
        self.pix_label.setPixmap(self.checkerboard_img.scaled(rat*self.width(),  rat*self.height(),  QtCore.Qt.KeepAspectRatio))

    def timeout_timer_cb(self,  evt):

        rospy.logerr("Timeout - no message arrived.")
        self.shutdown_ts()
        self.calibrated_pub.publish(self.calibrated)
        self.calibrating = False

    def tfl_delay_timer_cb(self,  evt=None):

        rospy.loginfo('Subscribing to camera topics')

        self.subs = []
        self.subs.append(message_filters.Subscriber(self.camera_image_topic, Image))
        self.subs.append(message_filters.Subscriber(self.camera_info_topic, CameraInfo))
        self.subs.append(message_filters.Subscriber(self.camera_depth_topic, Image))

        self.ts = message_filters.TimeSynchronizer(self.subs, 10)
        self.ts.registerCallback(self.sync_cb)

        self.timeout_timer = rospy.Timer(rospy.Duration(3.0),  self.timeout_timer_cb,  oneshot=True)

    def calibrate_srv_cb(self,  req):

        if self.calibrating:
            rospy.logwarn('Calibration already running')
            return None

        rospy.loginfo('Starting calibration')
        self.emit(QtCore.SIGNAL('show_chessboard'))
        self.calibrating = True

        self.calibration_attempts = 0

        # TF Listener needs some time to buffer data
        if self.tfl is None:
            self.tfl = tf.TransformListener()
            self.tfl_timer = rospy.Timer(rospy.Duration(3.0),  self.tfl_delay_timer_cb,  oneshot=True)
        else:
            self.tfl_delay_timer_cb()

        return EmptyResponse()

    def scene_cb(self,  msg):

        if not self.calibrated or self.calibrating: return

        np_arr = np.fromstring(msg.data, np.uint8)
        image_np = cv2.imdecode(np_arr, cv2.CV_LOAD_IMAGE_COLOR)

        image_np = cv2.warpPerspective(image_np, self.h_matrix, (self.width(), self.height()),  flags = cv2.INTER_LINEAR) # ,  flags=cv2.WARP_INVERSE_MAP

        #print image_np.nonzero()
        #print(image_np[image_np.nonzero()])
        #print

        #print image_np
        #print

        height, width, channel = image_np.shape
        bytesPerLine = 3 * width
        image = QtGui.QPixmap.fromImage(QtGui.QImage(image_np.data, width, height, bytesPerLine, QtGui.QImage.Format_RGB888))
        self.emit(QtCore.SIGNAL('scene'),  image)

    def scene_evt(self,  img):

        if self.calibrating: return

        # TODO warp image according to calibration
        self.pix_label.setPixmap(img)

    def is_calibrated(self):

        return True

    def on_resize(self, event):

        self.pix_label.resize(self.size())

