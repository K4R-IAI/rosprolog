#!/usr/bin/env python3

import rospy
import os
from gevent.pywsgi import WSGIServer  # Web Server
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.exceptions import BadRequest
from flask_restplus import Api, Resource, fields
from json_prolog_msgs.srv import PrologQuery, PrologNextSolution, PrologNextSolutionResponse, PrologFinish
import json


class RosprologRestClient:
    def __init__(self, name_space='rosprolog', timeout=None, wait_for_services=True):
        """
        @type 	name_space: str
        @param 	timeout: Amount of time in seconds spend waiting for rosprolog to become available.
        @type 	timeout: int
        """
        self.id = 0
        self._simple_query_srv = rospy.ServiceProxy(
            '{}/query'.format(name_space), PrologQuery)
        self._next_solution_srv = rospy.ServiceProxy(
            '{}/next_solution'.format(name_space), PrologNextSolution)
        self._finish_query_srv = rospy.ServiceProxy(
            '{}/finish'.format(name_space), PrologFinish)
        if wait_for_services:
            rospy.loginfo('waiting for {} services'.format(name_space))
            self._finish_query_srv.wait_for_service(timeout=timeout)
            self._simple_query_srv.wait_for_service(timeout=timeout)
            self._next_solution_srv.wait_for_service(timeout=timeout)
            rospy.loginfo('{} services ready'.format(name_space))

    def post_query(self, query):
        """
        @param	query: the query string
        @type		query: str
        """
        self.id += 1
        result = self._simple_query_srv(id=str(self.id), query=query)
        if result.ok:
            return True
        else:
            self.id -= 1
            return False

    def get_solutions(self, max_solution_count):
        """
        @param	solution_count: the query string
        @type		solution_count: int
        """
        solutions = []
        if max_solution_count > 0:
            try:
                while(len(solutions) < max_solution_count):
                    next_solution = self._next_solution_srv(id=str(self.id))
                    if next_solution.status == PrologNextSolutionResponse.OK:
                        solutions.append(
                            dict(json.loads(next_solution.solution)))
                    elif next_solution.status == PrologNextSolutionResponse.NO_SOLUTION:
                        if not solutions:
                            raise BadRequest('No solution found')
                        break
                    else:
                        raise BadRequest('Bad query')
            finally:
                self.finish_query()
        return solutions

    def finish_query(self):
        self._finish_query_srv(id=str(self.id))


# Set KnowRob version and KnowRob Port from environment variables
KNOWROB_VERSION = os.getenv('KNOWROB_VERSION')
if KNOWROB_VERSION is None:
    KNOWROB_VERSION = 'v1.0'
else:
    KNOWROB_VERSION = str(KNOWROB_VERSION)

KNOWROB_PORT = os.getenv('KNOWROB_PORT')
if KNOWROB_PORT is None:
    KNOWROB_PORT = 62226
else:
    KNOWROB_PORT = int(KNOWROB_PORT)

app = Flask(__name__)
app.config['RESTPLUS_MASK_SWAGGER'] = False
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_host=1)

# API titel
api = Api(app,
          version=KNOWROB_VERSION,
          title='KnowRob API',
          description='KnowRob API reference',
          )

# Query interface
query = api.model('Query', {
    'query': fields.String(required=True, description='The query string'),
    'maxSolutionCount': fields.Integer(required=True, default=100, description='The maximal number of solutions'),
    'response': fields.List(fields.Raw, readonly=True, description='The response list')
})

# Endpoint
ns = api.namespace('knowrob/api/' + KNOWROB_VERSION,
                   description='Operations related to KnowRob')


@ns.route("/query")
class Query(Resource):
    @ns.expect(query)  # input model
    @ns.marshal_with(query)
    def post(self):
        rosrest.post_query(api.payload['query'])
        api.payload['response'] = rosrest.get_solutions(
            api.payload['maxSolutionCount'])
        return api.payload


if __name__ == '__main__':
    rospy.init_node('rosprolog_rest', anonymous=True)

    # ROS Client for prolog
    rosrest = RosprologRestClient()

    http_server = WSGIServer(('', KNOWROB_PORT), app)
    http_server.serve_forever()
