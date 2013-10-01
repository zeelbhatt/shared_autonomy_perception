#! /usr/bin/env python

import math

import rospy

import actionlib
from cv_bridge import CvBridge
import handle_point_cloud2 as pts

from sensor_msgs.msg import Image, CameraInfo, PointCloud2
from shared_autonomy_msgs.msg import SegmentGoal, SegmentAction
from shared_autonomy_msgs.srv import KinectAssembly


# This code needs to:
# * obtain a set of data from the kinect_assembler
# * repackage it into the appropriate format
# * call the actionlib server that actually does segmentation
# * use the resulting mask to get desired image coords; use the point_cloud2 package to 

class RunSegmentation():

    def __init__(self):
        self.kinect_client = rospy.ServiceProxy('assemble_kinect', KinectAssembly)
        self.point_publisher = rospy.Publisher('segmented_points', PointCloud2)
        self.segment_client = actionlib.SimpleActionClient('/grabcut3d_segmentation_node', SegmentAction)

        self.mask = None

    def get_data(self):
        try:
            resp = self.kinect_client()
        except rospy.ServiceException:
            print "run_segmentation unable to get kinect data!"
            resp = None
            
        return resp

    def get_segmentation(self, data):
        self.segment_client.wait_for_server()    
        goal = SegmentGoal()
        goal.image = data.image
        goal.depth = data.depth

        # this callback will set the member variable mask
        self.segment_client.send_goal(goal, done_cb=self.segmentDoneCB, 
                                      feedback_cb=self.segmentFeedbackCB)
        self.segment_client.wait_for_result()
        
        return self.mask

    def publish_points(self, data, mask):
        print "I should be publishing points!"
        mybridge = CvBridge()
        img = mybridge.imgmsg_to_cv(mask)
        # TODO: I dislike having this dependency here on the cv encodings ... the binary transform should happen in grabcut3d_segmentation
        # list of foreground indices 
        # idxs = [[ii, jj] for jj in range(img.cols) for ii in range(img.rows) if (img[ii,jj] == 1 or img[ii,jj]==3)]
        pt_gen = pts.read_points(data.points)#, uvs=idxs, skip_nans=True) # this didn't work!!

        out_pts = []
        for jj in range(data.points.height):
            for ii in range(data.points.width):
                pt = pt_gen.next()
                if not math.isnan(pt[0]):
                    if (img[jj,ii] == 1 or img[jj,ii]==3):
                        out_pts.append(pt[0:3])
        print "done creating output point cloud"

        #pt_arr = array(pt_gen)#[pt for pt in pt_gen]
        #print pt_arr
        out_cloud = pts.create_cloud_xyz32(data.points.header, out_pts)

        # then, 
        self.point_publisher.publish(out_cloud)

    def segmentDoneCB(self, state, result):
        print "segmentation done"
        self.mask = result.mask
        
    def segmentFeedbackCB(self, feedback):
        print "feedback received"
        print feedback
    


if __name__ == "__main__":
    rospy.init_node('run_segmentation')

    mysegmenter = RunSegmentation()
    data = mysegmenter.get_data()
    if data is None:
        print "run_segmentation - no data available!"
        exit

    print "got image data"
    mask = mysegmenter.get_segmentation(data)
    print "got mask"
    mysegmenter.publish_points(data, mask)
