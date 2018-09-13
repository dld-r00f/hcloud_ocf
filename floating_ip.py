#!/usr/bin/python3
#
#   Resource Agent for managing hetzner cloud ips
#
#   License:      MIT
#   (c) 2018Sven Speckmaier

import ocf
import time
import shared
from hetznercloud import HetznerCloudClientConfiguration, HetznerCloudClient
from hetznercloud.floating_ips import HetznerCloudFloatingIp
from hetznercloud.exceptions import HetznerAuthenticationException, HetznerInternalServerErrorException, HetznerActionException, HetznerRateLimitExceeded

class IpFinder:
     def find(self, client, address) -> HetznerCloudFloatingIp:
         for floatingIp in client.floating_ips().get_all():
             if floatingIp.ip == address:
                 return floatingIp
         raise EnvironmentError('Floating ip not found.')

class FloatingIp(ocf.ResourceAgent):
    def __init__(self, ipFinder = IpFinder()):
        self.ipFinder = ipFinder

        ocf.ResourceAgent.__init__(self, 'floating_ip', '0.1.0', 'Manage Hetzner Cloud Floating Ips',
                '''
                This resource agent uses the hetzner cloud api and to manage a floating ip address.

                By default matching the host to a server entry in the api is done by matching its
                default ipv4 address to those listed in the api servers.
                This can be chaned using the host_finder parameter

                This resource does NOT manage adding the ip address to the network interface. You should either
                add it permanently to your network adapter by setting it in /etc/network/interfaces,
                /etc/netplan/* or in NetworkManager OR you could use a second resource of type IPAddr2
                with the address and set at least two constraints:
                colocation ip address with floating ip
                order start ip address after floating ip
                ''')

        self.floatingIp = ocf.Parameter('ip', shortDescription='Hetner Cloud Ip-Address x.x.x.x' ,
                description='''
                The Hetzner Cloud Floating Ip Address which this resource should manage.
                Note that this does not mean the Id of the Ip-Address but the Address
                itself.
                ''',
                required=True, unique=True)
        self.floatingIp.validate = shared.Ipv4Validator(self.floatingIp)
        self.apiToken = ocf.Parameter('api_token', shortDescription='Hetner Cloud api token' ,
                description='''
                The Hetzner Cloud api token with which the ip address can be managed.

                You can create this in the Hetner Cloud Console. Select the project
                which contains your Ip-Address, then select `Access` on the leftside menu
                Activate the second tab `Api Tokens` and create a new token.
                ''',
                required=True, unique=False)
        self.apiToken.validate = shared.StringLengthValidator(self.apiToken, 64)
        self.finderType = ocf.Parameter('host_finder', default='public-ip', shortDescription='Host finder' ,
                description='''
                Implementation to use for matching the host this agent is running on to the host in the api

                Available implementations:
                - public-ip: The public ipv4 address listed in the api is present on any adapter on the host
                - hostname: The hosts `hostname` matches the server name in the api
                ''',
                required=False, unique=False)
        self.sleep = ocf.Parameter('sleep', default='5', shortDescription='Sleep duration when an api request fails' ,
                description='''
                The number of seconds to wait when encountering a problem with the api.

                This happens mainly when the api is unreachable or returns internal server errors.
                Rate limit errors will wait for double the set time but at least 10 seconds.
                ''',
                required=False, unique=False)
        self.parameters = [
                self.floatingIp,
                self.apiToken,
                self.finderType,
                self.sleep
        ]
        self.setHint('start', 'timeout', '60')
        self.setHint('monitor', 'timeout', '60')
        self.wait = 0
        self.rateLimitWait = 0

    def getParameters(self):
        return self.parameters

    def populated(self):
        if not self.apiToken.get():
            return
        configuration = HetznerCloudClientConfiguration().with_api_key( self.apiToken.get() ).with_api_version(1)
        self.client = HetznerCloudClient(configuration)
        self.wait = int( self.sleep.get() )
        self.rateLimitWait = max( int( self.sleep.get() ) * 2, 10 )

    def start(self):
        hostFinder = shared.makeHostFinder( self.finderType.get() )
        try:
            success = False
            while not success:
                try:
                    server = hostFinder.find( self.client )
                    success = True
                except HetznerInternalServerErrorException:
                    time.sleep( self.wait )
                except HetznerRateLimitExceeded:
                    time.sleep( self.rateLimitWait )
                except EnvironmentError: 
                    # Host not found in api
                    return ocf.ReturnCodes.isMissconfigured

            success = False
            while not success:
                try:
                    ip = self.ipFinder.find( self.client, self.floatingIp.get() )
                    success = True
                except HetznerActionException:
                    time.sleep( self.wait )
                except HetznerInternalServerErrorException:
                    time.sleep( self.wait )
                except HetznerRateLimitExceeded:
                    time.sleep( self.rateLimitWait )

            # Ip already assigned, no action required
            if ip.server == server.id:
                return ocf.ReturnCodes.success
                

            success = False
            while not success:
                try:
                    ip.assign_to_server( server.id )
                    success = True
                except HetznerActionException:
                    time.sleep( self.wait )
                except HetznerInternalServerErrorException:
                    time.sleep( self.wait )
                except HetznerRateLimitExceeded:
                    time.sleep( self.rateLimitWait )
        except HetznerAuthenticationException:
            print('Error: Cloud Api returned Authentication error. Token deleted?')
            return ocf.ReturnCodes.isMissconfigured
        return ocf.ReturnCodes.success

    def stop(self):
        return ocf.ReturnCodes.success

    def monitor(self):
        isActive = False

        try:
            hostFinder = shared.makeHostFinder( self.finderType.get() )
            success = False
            while not success:
                try:
                    server = hostFinder.find( self.client )
                    success = True
                except HetznerActionException:
                    time.sleep( self.wait )
                except HetznerInternalServerErrorException:
                    time.sleep( self.wait )
                except HetznerRateLimitExceeded:
                    time.sleep( self.rateLimitWait )
                except EnvironmentError: 
                    # Host not found in api
                    return ocf.ReturnCodes.isMissconfigured

            success = False
            while not success:
                try:
                    ip = self.ipFinder.find( self.client, self.floatingIp.get() )
                    if ip.server == server.id:
                        isActive = True
                    success = True
                except HetznerInternalServerErrorException:
                    time.sleep( self.wait )
                except HetznerActionException:
                    time.sleep( self.wait )
                except HetznerRateLimitExceeded:
                    time.sleep( self.rateLimitWait )
        except HetznerAuthenticationException:
            print('Error: Cloud Api returned Authentication error. Token deleted?')
            return ocf.ReturnCodes.isMissconfigured

        if not isActive:
            return ocf.ReturnCodes.isNotRunning
            
        return ocf.ReturnCodes.success