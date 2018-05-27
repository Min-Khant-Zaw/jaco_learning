import numpy as np
import trajoptpy
import or_trajopt
import openravepy
from openravepy import *

import openrave_utils
from openrave_utils import *

if __name__ == '__main__':
	if len(sys.argv) < 1:
		print "ERROR: Not enough arguments. Specify trajectory pathfile"
	else:
		traj_path = int(sys.argv[1])

    # initialize robot and empty environment
	model_filename = 'jaco_dynamics'
	env, robot = initialize(model_filename)

	# insert any objects you want into environment
	bodies = []

	# plot the table and table mount
	plotTable(env)
    plotTableMount(env,bodies)

	here = os.path.dirname(os.path.realpath(__file__))
	trajs = pickle.load( open( here + traj_path, "rb" ) )

    for waypts_plan in trajs:
        plotTraj(env,robot,bodies,waypts_plan, size=10,color=[0, 0, 1])
