#!/usr/bin/env python

from PyQt4 import QtGui, QtCore, QtNetwork
from art_projected_gui.items import ObjectItem, PlaceItem, LabelItem, ProgramItem, PolygonItem
import rospy
from art_projected_gui.helpers import conversions
from art_msgs.srv import NotifyUserRequest


class customGraphicsView(QtGui.QGraphicsView):

    def __init__(self, parent=None):
        QtGui.QGraphicsView.__init__(self, parent)

        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

    def resizeEvent(self, evt=None):

        self.fitInView(self.sceneRect(), QtCore.Qt.KeepAspectRatio)


class UICore(QtCore.QObject):
    """Class holds QGraphicsScene and its content (items).

    There are methods for manipulation (add, find, delete) with items.
    There should not be any ROS-related stuff, just basic things.
    All items to be displayed (objects, places etc.) are inserted into array with few exceptions (e.g. program visualization, notifications).

    Attributes:
        x (float): x coordinate of the scene's origin (in world coordinate system, meters).
        y (float): dtto.
        width (float): Width of the scene.
        height (float): dtto
        rpm (int): Resolution per meter (pixels per meter of width/height).
        scene (QGraphicsScene): Holds all Item(s), manages (re)painting etc.
        bottom_label (LabelItem): Label for displaying messages to user.
        program_vis (ProgramItem): Item to display robot's program.
        scene_items (list): Array to hold all displayed items.
        view (QGraphicsView): To show content of the scene in debug window.
    """

    def __init__(self, x, y, width, height, rpm,  scene_server_port):
        """
        Args:
            x (float): x coordinate of the scene's origin (in world coordinate system, meters).
            y (float): dtto.
            width (float): Width of the scene.
            height (float): dtto
            rpm (int): Resolution per meter (pixels per meter of width/height).
        """

        super(UICore, self).__init__()

        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.rpm = rpm
        self.port = scene_server_port

        w = self.width * self.rpm
        h = self.height / self.width * w

        self.scene = QtGui.QGraphicsScene(0, 0, int(w), int(h))
        self.scene.setBackgroundBrush(QtCore.Qt.black)
        # self.scene.setItemIndexMethod(QtGui.QGraphicsScene.NoIndex) # should be good for dynamic scenes

        self.scene_items = []

        self.bottom_label = LabelItem(self.scene, self.rpm, 0.2, 0.05, self.width - 0.4, 0.05)

        self.scene_items.append(self.bottom_label)

        self.selected_object_ids = []
        self.selected_object_types = []

        self.view = customGraphicsView(self.scene)
        self.view.setRenderHint(QtGui.QPainter.Antialiasing)
        self.view.setViewportUpdateMode(QtGui.QGraphicsView.SmartViewportUpdate)
        self.view.setStyleSheet("QGraphicsView { border-style: none; }")

        QtCore.QObject.connect(self, QtCore.SIGNAL('send_scene'), self.send_to_clients_evt)

        self.tcpServer = QtNetwork.QTcpServer(self)
        if not self.tcpServer.listen(port=self.port):

            rospy.logerr('Failed to start scene TCP server on port ' + str(self.port))

        self.tcpServer.newConnection.connect(self.new_connection)
        self.connections = []

        self.last_scene_update = None
        self.scene.changed.connect(self.scene_changed)

    def new_connection(self):

        rospy.loginfo('Some projector node just connected.')
        self.connections.append(self.tcpServer.nextPendingConnection())
        self.connections[-1].setSocketOption(QtNetwork.QAbstractSocket.LowDelayOption, 1)
        self.emit(QtCore.SIGNAL('send_scene'), self.connections[-1])
        # TODO deal with disconnected clients!
        # self.connections[-1].disconnected.connect(clientConnection.deleteLater)

    def send_to_clients_evt(self, client=None):

        # if all connections are sending scene image, there is no need to render the new one
        if client is None:

            for con in self.connections:

                if con.bytesToWrite() == 0:
                    break

            else:
                return

        # TODO try to use Format_RGB16 - BMP is anyway converted to 32bits (send raw data instead)
        pix = QtGui.QImage(self.scene.width(), self.scene.height(), QtGui.QImage.Format_ARGB32_Premultiplied)
        painter = QtGui.QPainter(pix)
        self.scene.render(painter)
        painter.end()

        block = QtCore.QByteArray()
        out = QtCore.QDataStream(block, QtCore.QIODevice.WriteOnly)
        out.setVersion(QtCore.QDataStream.Qt_4_0)
        out.writeUInt32(0)

        img = QtCore.QByteArray()
        buffer = QtCore.QBuffer(img)
        buffer.open(QtCore.QIODevice.WriteOnly)
        pix.save(buffer, "BMP")
        out << QtCore.qCompress(img, 1)  # this seem to be much faster than using PNG compression

        out.device().seek(0)
        out.writeUInt32(block.size() - 4)

        # print block.size()

        if client is None:

            for con in self.connections:

                if con.bytesToWrite() > 0:
                    return
                con.write(block)

        else:

            client.write(block)

    def scene_changed(self, rects):

        if len(rects) == 0:
            return
        # TODO Publish only changes? How to accumulate them (to be able to send it only at certain fps)?

        now = rospy.Time.now()
        if self.last_scene_update is None:
            self.last_scene_update = now
        else:
            if now - self.last_scene_update < rospy.Duration(1.0 / 20):
                return

        # print 1.0/(now - self.last_scene_update).to_sec()
        self.last_scene_update = now

        self.emit(QtCore.SIGNAL('send_scene'))

    def notif(self, msg, min_duration=3.0, temp=False, message_type=NotifyUserRequest.INFO):
        """Display message (notification) to the user.

        Args:
            msg (str): Message to be displayed.
            min_duration (:obj:`float`, optional): Message should be displayed for min_duration seconds at least.
            temp (:obj:`bool`, optional): temporal message disappears after min_duration and last non-temporal message is displayed instead.
        """

        self.bottom_label.add_msg(msg, message_type,  rospy.Duration(min_duration), temp)

    def debug_view(self):
        """Show window with scene - for debugging purposes."""

        self.view.show()

    def get_scene_items_by_type(self, itype):
        """Generator to filter content of scene_items array."""

        for el in self.scene_items:
            if type(el) is itype:  # TODO option for 'isinstance' ??
                yield el

    def remove_scene_items_by_type(self, itype):
        """Removes items of the given type from scene (from scene_items and scene)."""

        its = []

        for it in self.scene_items:

            if type(it) is not itype:
                continue
            its.append(it)

        for it in its:

            self.scene.removeItem(it)
            self.scene_items.remove(it)

    def add_object(self, object_id, object_type, x, y, yaw,  sel_cb=None):
        """Adds object to the scene.

        Args:
            object_id (str): unique object ID
            object_type (str): type (category) of the object
            x, y (float): world coordinates
            sel_cb (method): Callback which gets called one the object is selected.
        """

        obj = ObjectItem(self.scene, self.rpm, object_id, object_type, x, y, yaw,  sel_cb)
        self.scene_items.append(obj)

        if object_id in self.selected_object_ids or object_type.name in self.selected_object_types:

            obj.set_selected(True)

    def remove_object(self, object_id):
        """Removes ObjectItem with given object_id from the scene."""

        obj = None

        for it in self.get_scene_items_by_type(ObjectItem):

            if it.object_id == object_id:

                obj = it
                break

        if obj is not None:

            self.scene.removeItem(obj)
            self.scene_items.remove(obj)
            return True

        return False

    def select_object(self, obj_id, unselect_others=True):
        """Sets ObjectItem with given obj_id as selected. By default, all other items are unselected."""

        if unselect_others:
            self.selected_object_ids = []

        if obj_id not in self.selected_object_ids:
            self.selected_object_ids.append(obj_id)

        for it in self.get_scene_items_by_type(ObjectItem):

            if it.object_id == obj_id:

                it.set_selected(True)
                if not unselect_others:
                    break

            elif unselect_others:

                it.set_selected(False)

    def select_object_type(self, obj_type_name, unselect_others=True):
        """Sets all ObjectItems with geiven object_type and selected. By default, all objects of other types are unselected."""

        if unselect_others:
            self.selected_object_types = []

        if obj_type_name not in self.selected_object_types:
            self.selected_object_types.append(obj_type_name)

        for it in self.get_scene_items_by_type(ObjectItem):

            if it.object_type.name == obj_type_name:
                it.set_selected(True)
            elif unselect_others:
                it.set_selected(False)

    def get_object(self, obj_id):
        """Returns ObjectItem with given object_id or None if the ID is not found."""

        for it in self.get_scene_items_by_type(ObjectItem):

            if it.object_id == obj_id:
                return it

        return None

    def add_place(self, caption,  pose_stamped, object_type,  object_id=None,  place_cb=None, fixed=False):

        # TODO check frame_id in pose_stamped and transform if needed
        self.scene_items.append(
            PlaceItem(
                self.scene,
                self.rpm,
                caption,
                pose_stamped.pose.position.x,
                pose_stamped.pose.position.y,
                object_type,
                object_id,
                place_pose_changed=place_cb,
                fixed=fixed,
                yaw=conversions.quaternion2yaw(pose_stamped.pose.orientation)
                )
            )

    def add_polygon(self, caption, obj_coords=[], poly_points=[], polygon_changed=None, fixed=False):

        self.scene_items.append(PolygonItem(self.scene, self.rpm, caption, obj_coords, poly_points, polygon_changed, fixed))

    def clear_places(self):

        self.remove_scene_items_by_type(PlaceItem)

    def clear_all(self):

        self.selected_object_ids = []
        self.selected_object_types = []

        for it in self.get_scene_items_by_type(ObjectItem):

            it.set_selected(False)

        self.remove_scene_items_by_type(PlaceItem)
        self.remove_scene_items_by_type(PolygonItem)
