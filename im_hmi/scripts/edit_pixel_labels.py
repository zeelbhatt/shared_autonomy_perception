from math import pi

from cv_bridge import CvBridge
import im_utils
from geometry_msgs.msg import Point
from interactive_markers.interactive_marker_server import *
from interactive_markers.menu_handler import *        
from shared_autonomy_msgs.msg import Pixel
from std_msgs.msg import ColorRGBA
import tf

# Lots of code copied from boundingbox, as it's also displaying images
class EditPixelLabels():
    def __init__(self, hmi_callback, im_server, image, mask):
        self.hmi_callback = hmi_callback
        self.im_server = im_server

        self.frame_id = image.header.frame_id
        cv_bridge = CvBridge()
        self.image = cv_bridge.imgmsg_to_cv(image)
        self.mask = cv_bridge.imgmsg_to_cv(mask)

        # pixels-per-m for published markers
        self.ppm = rospy.get_param("~ppm", 100)

        # lists of pixels that'll be returned
        self.fg = []
        self.bg = []

        # draws the image using interactive markers
        self.add_image()
        # creates the button that'll be the done callback
        self.add_button()

    # used to set the im_server back to initial state ... 
    def cancel(self):
        self.im_server.clear()
        self.im_server.applyChanges()

    def add_image(self):
        rospy.loginfo("add image called!")

        menu_handler = MenuHandler()
        menu_foreground = menu_handler.insert("Foreground", callback=self.foreground_cb)
        menu_background = menu_handler.insert("Background", callback=self.background_cb)

        image_marker = Marker()
        image_marker.type = image_marker.POINTS
        image_marker.scale.x = 0.05
        image_marker.scale.y = 0.05
        image_marker.scale.z = 0.05

        # displaying every pixel is too much; downsample before turning image into IM
        for col in xrange(0, self.image.cols, 3):
            for row in xrange(0, self.image.rows, 3):
                # sinking it a bit s.t. the Interactive Markers are easier to grab
                (xx, yy) = im_utils.metersFromPixels(row, col, self.ppm, self.image.rows, self.image.cols)



                mask_val = self.mask[row,col]
                (red, green, blue) = im_utils.rosFromCVbridgeColor(self.image[row,col])
                # TODO: these are magic numbers from opencv, indicating forground/probable foreground
                # (in OpenCV, they're cv::GC_FGC cf::GC_PR_FGD)
                if (mask_val == 1) or (mask_val == 3):
                    pt = Point(xx, yy, 0.0)
                    cc = ColorRGBA(red, green, blue, 1.0)
                else:
                    # putting this one literally in the background
                    pt = Point(xx, yy, -0.5)
                    grey = im_utils.greyFromRGB(red, green, blue)
                    # int is required in order to not be random shades! 0.5 makes it lighter                
                    grey = max(int(0.5*grey),1)
                    cc = ColorRGBA(grey, grey, grey, 0.5)
                image_marker.points.append(pt)
                image_marker.colors.append(cc)

        image_control = InteractiveMarkerControl()
        image_control.always_visible = True
        image_control.interaction_mode = InteractiveMarkerControl.MENU
        image_control.markers.append(image_marker)

        image_im = InteractiveMarker()
        image_im.header.frame_id = self.frame_id
        image_im.name = "LabeledImage"
        image_im.description = ""
        image_im.controls.append(image_control)

        self.im_server.insert(image_im)
        menu_handler.apply(self.im_server, "LabeledImage")
        self.im_server.applyChanges()

    def foreground_cb(self, feedback):
        if feedback.mouse_point_valid:
            (row, col) = im_utils.pixelsFromMeters(feedback.mouse_point.x, feedback.mouse_point.y, 
                                                   self.ppm, self.image.rows, self.image.cols)
            self.fg.append(Pixel(col, row))

    def background_cb(self, feedback):
        if feedback.mouse_point_valid:
            (row, col) = im_utils.pixelsFromMeters(feedback.mouse_point.x, feedback.mouse_point.y,
                                                   self.ppm, self.image.rows, self.image.cols)
            self.bg.append(Pixel(col, row))

    def add_button(self):
        button_marker = Marker()
        button_marker.type = button_marker.TEXT_VIEW_FACING
        button_marker.scale.z = 1.0 # height of letter A
        button_marker.pose.position.x = 3.2
        button_marker.pose.position.y = -0.5
        button_marker.pose.position.z = 0.0
        button_marker.color.r = 0.5
        button_marker.color.g = 0.5
        button_marker.color.b = 0.5
        button_marker.color.a = 1.0

        button_marker.text = "Done Labeling"

        button_control = InteractiveMarkerControl()
        button_control.always_visible = False
        button_control.interaction_mode = button_control.BUTTON
        button_control.name = "DoneLabeling"
        button_control.markers.append(button_marker)

        button_im = InteractiveMarker()
        button_im.header.frame_id = self.frame_id
        button_im.name = "DoneLabeling"
        button_im.description = ""
        button_im.controls.append(button_control)

        self.im_server.insert(button_im)
        self.im_server.setCallback(button_im.name, self.done_labelling_cb)
        self.im_server.applyChanges()


    # called when done button is clicked; cleans up the IMs, and lets 
    # the main GUI know that labeling has finished
    def done_labelling_cb(self, feedback):
        self.im_server.clear()
        self.im_server.applyChanges()
        self.hmi_callback()

    def get_foreground(self):
        return self.fg

    def get_background(self):
        return self.bg
