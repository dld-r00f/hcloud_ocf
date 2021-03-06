#!/usr/bin/python3
import sys
import os
sys.path.append( os.path.dirname( os.path.realpath(__file__) ) + '/../../stonith' )
import time
import unittest
import stonith_agent
import stonith
import hetznercloud
import CallsBase
from unittest import mock
from mock import Mock
from mock import patch

class TestHetznerCloud(CallsBase.TestBase, unittest.TestCase):

    def takeAction(self, agent):
        return agent.powerOff()

    def serverAction(self, server):
        return server.power_off


if __name__ == '__main__':
    unittest.main()
