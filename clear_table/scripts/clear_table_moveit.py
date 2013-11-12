#! /usr/bin/env python

# This is the version of Clear Table that uses Hydro's version of moveit to actually do the pickup tasks

import math

import rospy

import actionlib
from cv_bridge import CvBridge
import handle_point_cloud2 as pts
import sensor_msgs # for converting point clouds
import smach
import smach_ros

from actionlib_msgs.msg import GoalStatus
from object_manipulation_msgs.srv import FindClusterBoundingBox2, FindClusterBoundingBox2Request
from sensor_msgs.msg import PointCloud2
from shared_autonomy_msgs.msg import SegmentGoal, SegmentAction
from shared_autonomy_msgs.srv import KinectAssembly


class Home(smach.State):
    def __init__(self):
        smach.State.__init__(self, outcomes=['at_home'])
    def execute(self, userdata):
        return 'at_home'
                             

class Segment(smach.State):
    def __init__(self):
        smach.State.__init__(self, 
                             outcomes=['done_segmenting', 'no_data', 'segmentation_failed', 'no_objects'], 
                             output_keys=['object_points'])

        print 'initializing Segment'

        self.kinect_client = rospy.ServiceProxy('head_mount_kinect/assemble_kinect', KinectAssembly)
        self.point_publisher = rospy.Publisher('segmented_points', PointCloud2)
        self.segment_client = actionlib.SimpleActionClient('segment_service', SegmentAction)


    def execute(self, userdata):

        print "waiting for assemble_kinect service"
        rospy.wait_for_service('head_mount_kinect/assemble_kinect')
        print "... got service"

        print "waiting for segmentation server"
        self.segment_client.wait_for_server()    
        print "... got segmentation server"

        try:
            kinect_data = self.kinect_client()
        except rospy.ServiceException:
            print 'clear_table unable to get kinect data!'
            rospy.sleep(5.0)
            return 'no_data'
        
        goal = SegmentGoal()
        goal.image = kinect_data.image
        goal.depth = kinect_data.depth

        print "Attempting to get segmentation"
        self.mask = None
        self.segment_client.send_goal(goal)
        self.segment_client.wait_for_result()
        if self.segment_client.get_state() != GoalStatus.SUCCEEDED:
            return 'segmentation_failed'
        result = self.segment_client.get_result()
        self.mask = result.mask
        print "... got segmentation"

        points = self.get_point_cloud(kinect_data, result.mask)
        self.point_publisher.publish(points)
        userdata.object_points = points

        return 'done_segmenting'

    def get_point_cloud(self, data, mask):
        print "I should be publishing points!"
        mybridge = CvBridge()
        img = mybridge.imgmsg_to_cv(mask)

        # TODO: depend on the read_points that should be in common_msgs?
        # TODO: why didn't the uvs=idxs code work? x
        pt_gen = pts.read_points(data.points)#, uvs=idxs, skip_nans=True) # this didn't work!!

        out_pts = []
        for jj in range(data.points.height):
            for ii in range(data.points.width):
                pt = pt_gen.next()
                if not math.isnan(pt[0]):
                    if (img[jj,ii] == 1 or img[jj,ii]==3):
                        out_pts.append(pt[0:3])
        print "done creating output point cloud"

        out_cloud = pts.create_cloud_xyz32(data.points.header, out_pts)
        return out_cloud


class GenerateGrasps(smach.State):
    def __init__(self):
        smach.State.__init__(self,
                             outcomes = ['no_grasp'], 
                             input_keys = ['object_points'])
        self.bb_client = rospy.ServiceProxy('/find_cluster_bounding_box2', FindClusterBoundingBox2)
    def execute(self, userdata):
        # TODO: no! there's a pointcloud2 version of the service as well!
        print 'waiting for cluster bb server'
        rospy.wait_for_service('find_cluster_bounding_box2')
        print '...got service'

        bb_req = FindClusterBoundingBox2Request()
        bb_req.cluster = userdata.object_points

        try:   
            bb_resp = self.bb_client(bb_req)
        except rospy.ServiceException:
            print 'no response from cluster bb server!'
            return 'no_grasp'

        print bb_resp

        return 'no_grasp'

# ready -> segment -> bbox + update environment (pass on object name) -> grasps (pass on generated grasps + object name) -> pickup -> drop -> reset
def main():
    rospy.init_node('clear_table')
    sm = smach.StateMachine(outcomes=['DONE'])
    
    # TODO: I'm avoiding makign the remapping explicit. May need to in the future. 
    with sm:
        smach.StateMachine.add('HOME', Home(),
                               transitions = {'at_home':'SEGMENT'})
        smach.StateMachine.add('SEGMENT', Segment(),
                               transitions = {'done_segmenting':'GENERATE_GRASPS',
                                              'segmentation_failed':'SEGMENT',
                                              'no_data':'SEGMENT',
                                              'no_objects':'HOME'})# NYI
        smach.StateMachine.add('GENERATE_GRASPS', GenerateGrasps(),
                               transitions = {'no_grasp':'HOME'})
        #                                      'grasp_found':'PICKUP'})
        #        smach.StateMachine.add('PICKUP', Pickup(),
        #                               transitions = {'pickup_failed':'HOME',
        #                                              'pickup_done':'DROP'})
        #        smach.StateMachine.add('DROP', Drop(),
        #                               transitions = {'drop_done':'HOME'})

    sis = smach_ros.IntrospectionServer('clear_table_sis', sm, '/SM_ROOT')
    sis.start()
    
    outcome = sm.execute()

    rospy.spin()
    sis.stop() 


if __name__ == "__main__":
    main()
