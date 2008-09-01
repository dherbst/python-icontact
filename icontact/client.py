# Copyright 2008   Online Agility (www.onlineagility.com)
# 
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
# 
#        http://www.apache.org/licenses/LICENSE-2.0
# 
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
"""
iContact API client library.

The module exposes the IContactClient class, which supports most iContact
API operations

Requirements
------------
- Python 2.5+
- dateutil library (http://labix.org/python-dateutil)
- Python logging

References
----------
iContact API documentation:
http://app.intellicontact.com/icp/pub/api/doc/api.html

To register an API client application, or to look up
the API Key and Shared Secret credentials for your
application, log in to the iContact web site and visit:
http://www.icontact.com/icp/core/registerapp    

To grant access to an API application and set an API client
password, visit: http://www.icontact.com/icp/core/externallogin

Author
------
James Murty
"""
import md5
import random
import time
import httplib
import urllib
import urlparse
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from datetime import datetime, tzinfo, timedelta
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement
import logging

class IContactClient:
    """Perform operations on the iContact API."""
    
    ICONTACT_API_URL = 'http://api.icontact.com/icp/core/api/v1.0/'
    NAMESPACE = 'http://www.w3.org/1999/xlink'
                
    def __init__(self, api_key, shared_secret, username, md5_password, 
        auth_handler=None, max_retry_count=5):
        """
        - api_key: the API Key assigned for the OA iContact client
        - shared_secret: a shared secret credential assigned to the OA 
          iContact client.
        - username: the iContact web site login username
        - password_md5: an MD5 hash of the user's API client password.
          This is the password registered for the API client, also known 
          as the "API Application Password". It is *not* the standard 
          web site login password.
        - max_retry_count: (Optional) Retry limit for logins or 
          rate-limited operations.
        - auth_handler: (Optional) An object that implements two callback
          methods that this client will invoke when it generates, or 
          requires, authentication credentials. The authentication handler
          object can be used to easily share credentials among multiple
          IContactClient instances.
          
        The authentication handler object must implement credential
        getter and setter methods::          
          get_credentials() => (token,sequence)
          set_credentials(token,sequence)
        """
        self.api_key = api_key
        self.shared_secret = shared_secret
        self.username = username
        self.md5_password = md5_password
        self.auth_handler = auth_handler
        self.log = logging.getLogger('icontact')
        self.max_retry_count = max_retry_count
        
        # Authentication information - (re-)populated by login operation
        if self.auth_handler:
            self.token, self.sequence = self.auth_handler.get_credentials()
        else:
            self.token = None
            self.sequence = 0
        
        # Track number of retries we have performed
        self.retry_count = 0
        
    def __calc_signature(self, call_path, params):
        """
        Calculates a signature value to authorize an iContact API call. 

        The signature is an MD5 hash of a string combining the 
        following items with no delimiters:
        - the Shared Secret for the API application 
          (`self.shared_secret`)
        - call_path: the API call path
        - params: request parameters sorted in alphabetical order

        A sample API request string that is generated and signed
        by this method (ignore capitalization, it's only for clarity)::
          SHAREDSECRETcallpathPARAM1NAMEparam1valuePARAM2NAMEparam2value
        """
        # Remove api_sig from params if it's present, otherwise it will ruin the signature.
        if params.has_key('api_sig'):
            del params['api_sig']
        
        params_string = ''.join(map(lambda x:x + str(params[x]), sorted(params)))
        string_to_sign = ''.join((self.shared_secret, call_path, params_string))
        signature = md5.new(string_to_sign).hexdigest()
        self.log.debug(u"String to sign: '%s' Signature: '%s'" % (string_to_sign, signature))
        return signature
        
    def __do_request(self, call_path, parameters={}):
        """
        Performs an API request and returns the resultant XML document as an
        xml.etree.ElementTree node. An Exception is thrown if the operation 
        results in an error response from iContact, or if there is no
        authentication information available (ie login has not been called)        
                
        This method does all the hard work for API operations: building the 
        URL path; signing the request; sending the request to iContact; 
        evaluating the response; and parsing the respones to an XML node.
        """
        # Check whether this method call was a retry that exceeds the retry limit
        if self.retry_count > self.max_retry_count:
            raise ExcessiveRetriesException("Exceeded maximum retry count (%d)" % self.max_retry_count)
        
        params = dict(parameters)
        
        # Parameter set must always include the API Key
        params.update(api_key=self.api_key)
        
        # All API operations except login also require the authentication 
        # token and sequence values obtained with a prior login operation.
        if not call_path.startswith('auth/login'):
            if not self.token:
                # Client is not logged in, do so now
                self.retry_count += 1
                self.log.debug(u"Login attempt %d of %d" % (self.retry_count, self.max_retry_count))
                self.login()
            params.update(api_tok=self.token, api_seq=self.sequence)
        
        # Generate the request's signature and add to parameters
        params.update(api_sig=self.__calc_signature(call_path, params))
        
        # PUT messages include the 'api_put' parameter
        if params.has_key('api_put'):
            api_put = params['api_put']
            # Remove this parameter from params, so it isn't included in the URL
            del(params['api_put'])
        else:
            api_put = None
        
        url = "%s%s?%s" % (self.ICONTACT_API_URL, call_path, urllib.urlencode(params))        
        self.log.debug(u"Invoking API method %s with URL: %s" % (api_put and 'PUT' or 'GET', url))
                
        if api_put:
            # Perform a PUT request
            self.log.debug(u'PUT Request body: %s' % api_put)
            scheme, host, path, params, query, fragment = urlparse.urlparse(url)
            conn = httplib.HTTPConnection(host, 80)            
            conn.request('PUT', path + '?' + query, api_put)
            response = conn.getresponse()
        else:
            # Perform a GET request
            response = urllib.urlopen(url)        

        xml = ElementTree.fromstring(response.read())
        self.log.debug(u'Response body:\n%s' % ElementTree.tostring(xml))
            
        if xml.get('status') != 'success':
            error_code = xml.find('error_code').text
            if error_code == '503':
                # We have been rate-limited, wait for a little while and try again.
                # TODO: Use a more sophisticated delay/backoff strategy?
                self.retry_count += 1
                self.log.warn(u"Exceeded iContact API rate limit of 1 request per second, " + \
                        "will perform retry %d of %d after a short delay" \
                        % (self.retry_count, self.max_retry_count))
                time.sleep(random.random() * self.retry_count) # Simplistic retry backoff algorithm
                return self.__do_request(call_path, params)
            elif error_code == '401':
                # Hacky test of the reason for auth failure. We can only recover from auth failures
                # due to invalid/expired tokens. Other situations, such as an auth failure caused 
                # by accessing a resource owned by someone else, cannot be recovered from.
                error_message = xml.find('error_message').text
                if error_message != 'Authorization problem.  Access not allowed.':
                    raise ClientException("Unrecoverable authentication error for %s: %s - %s" % \
                        (call_path, error_code, error_message))                    
                
                # Client is not logged in, or the authorization has gone stale. Log in again.
                time.sleep(random.random() * self.retry_count) # Simplistic retry backoff algorithm
                self.retry_count += 1
                self.log.warn(u"Login attempt %d of %d" % (self.retry_count, self.max_retry_count))
                self.login()
                return self.__do_request(call_path, params)
            else:
                raise ClientException("Unrecoverable error for %s: %s - %s" %\
                    (call_path, error_code, xml.find('error_message').text))
        # Reset retry count to 0 since we have a successful response
        self.retry_count = 0                
        return xml        

    def __parse_stats(self, node):
        """
        Parses statistics information from a 'stats' XML node that will
        be present in an iContact API response to the 
        message_delivery_details and message_stats methods. The parsed
        information is returned as a dictionary of dictionaries.        
        """
        def summary_to_dict(stats_node):
            if stats_node == None:
                return None
            summary = dict(
                count=int(stats_node.get('count') or '0'),
                percent=float(stats_node.get('percent')),
                href=stats_node.get('{%s}href' % self.NAMESPACE))
            if stats_node.get('unique'):
                summary['unique'] = int(stats_node.get('unique'))
            return summary            
        
        results = dict(
            released=summary_to_dict(node.find('released')),
            bounces=summary_to_dict(node.find('bounces')),
            unsubscribes=summary_to_dict(node.find('unsubscribes')),
            opens=summary_to_dict(node.find('opens')),
            clicks=summary_to_dict(node.find('clicks')),
            forwards=summary_to_dict(node.find('forwards')),
            comments=summary_to_dict(node.find('comments')),
            complaints=summary_to_dict(node.find('complaintss'))
        )   
        contacts=[]
        for c in node.findall('*/contact'):
            contact = dict(
                email=c.get('email'),
                name=c.get('name'),
                href=c.get('{%s}href' % self.NAMESPACE))
            dates = []
            for date_node in c.findall('*'):
                dates.append(parse(date_node.get('date')))
            contact['dates'] = dates
            contacts.append(contact)
        results['contacts'] = contacts
        return results
    
    def login(self):    
        """
        Logs in to the iContact API system and obtains a tuple containing
        a token string and a sequence integer that can be used to authenticate
        the client in susequent API operations. 
        
        The token and sequence values are stored in the `token` and `sequence`
        class member variables, and are also returned as a tuple.
        
        There is no need to call this method directly, as this client will
        automatically log in if/when necessary.
        
        NOTE: This method cannot log in to iContact accounts with multiple 
        client folders.
        """
        xml = self.__do_request('auth/login/%s/%s' % (self.username, self.md5_password))
        
        # Store the authentication token and sequence values for use in subsequent operations.
        self.token = xml.find('auth/token').text
        self.sequence = int(xml.find('auth/seq').text)
        self.log.debug(u'Client authenticated. Token: %s  Sequence: %d' % (self.token, self.sequence))
        
        # If an authentication handler is available, notify it of the latest credentials
        if self.auth_handler:
            self.auth_handler.set_credentials(self.token, self.sequence)
                    
        return (self.token, self.sequence)
    
    def lists(self):
        """
        Returns iContact Lists as an array of tuples, each of which contains
        a list identifier (int) and URL fragment (str). For example::
          [(1, '/list/1'), (3, '/list/3')]
        """
        xml = self.__do_request('lists')
        lists = []
        for list in xml.findall('lists/list'):
            id = int(list.get('id'))
            href = list.get('{%s}href' % self.NAMESPACE)
            lists.append((id, href))
        return lists
    
    def list(self, list_id):
        """
        Returns a dictionary of information about the iContact List 
        identified by the given id number. The dictionary includes:
        - id (int)                 - href (str)         
        - name (str)               - description (str)        
        - ownerreceipt (Boolean)   - systemwelcome (Boolean)
        - signupwelcome (Boolean)  - welcome_html (str)
        - welcome_text (str)       - optin_html (str)
        - optin_text (str)
        """
        xml = self.__do_request('list/%s' % list_id)
        
        list = xml.find('list')
        return dict(id=int(list.get('id')) , href=list.get('{%s}href' % self.NAMESPACE), \
            name=list.find('name').text, description=list.find('description').text, \
            ownerreceipt=list.find('ownerreceipt').text == '1', \
            systemwelcome=list.find('systemwelcome').text == '1', \
            signupwelcome=list.find('signupwelcome').text == '1', \
            welcome_html=list.find('welcome_html').text, 
            welcome_text=list.find('welcome_text').text, 
            optin_html=list.find('optin_html').text, 
            optin_text=list.find('optin_text').text)
        
    def campaigns(self):
        """
        Returns iContact Campaigns as an array of tuples, each of which contains
        a campaign identifier (int) and URL fragment. For example::
          [(1, '/campaign/1'), (3, '/campaign/3')]
        """
        xml = self.__do_request('campaigns')
        lists = []
        for list in xml.findall('campaigns/campaign'):
            id = int(list.get('id'))
            href = list.get('{%s}href' % self.NAMESPACE)
            lists.append((id, href))
        return lists

    def campaign(self, campaign_id):
        """
        Returns a dictionary of information about the iContact Campaign 
        identified by the given id number. The dictionary includes:
        - id (int)                  - href (str)         
        - name (str)                - description (str)        
        - fromname (str)            - fromemail (str)
        - street (str)              - city (str)
        - state (str)               - zip (str)
        - country (str)             - archivebydefault (Boolean)              
        - publicarchiveurl (str)    - useaccountaddress (Boolean)
        """
        xml = self.__do_request('campaign/%s' % campaign_id)

        campaign = xml.find('campaign')
        return dict(id=int(campaign.get('id')), \
            href=campaign.get('{%s}href' % self.NAMESPACE), \
            name=campaign.find('name').text, \
            description=campaign.find('description').text, \
            fromname=campaign.find('fromname').text, \
            fromemail=campaign.find('fromemail').text, \
            street=campaign.find('street').text, \
            city=campaign.find('city').text, \
            state=campaign.find('state').text, \
            zip=campaign.find('zip').text, \
            country=campaign.find('country').text, \
            publicarchiveurl=campaign.find('publicarchiveurl').text, \
            archivebydefault=campaign.find('archivebydefault').text == '1', \
            useaccountaddress=campaign.find('useaccountaddress').text == '1')

    def contacts(self, **kwargs):
        """
        Returns iContact contacts that match given constraints as an array of 
        tuples, each of which contains a contact identifier (int) and URL 
        fragment. For example::
          [(1, '/contact/1'), (3, '/contact/3')]
        
        If you provide constraints to this method, only contacts that match
        those constraints will be returned, otherwise all contacts will be
        returned. Constraints can include '*' wildcard characters.
        
        Valid constraints can use any contact field (see contact.__doc__) 
        and the comparison value is not case-sensitive. For example::
          email=username@somewhere.com
          email=*@somewhere.com
          lname=Jones
          fname=terry
          state=nsw
        """
        xml = self.__do_request('contacts', kwargs)
        
        contacts = []
        for list in xml.findall('contact'):
            id = int(list.get('id'))
            href = list.get('{%s}href' % self.NAMESPACE)
            contacts.append((id, href))
        return contacts

    def contact(self, contact_id):
        """
        Returns a dictionary of information about the iContact contact 
        identified by the given id number. The dictionary includes the
        following fields (only * items are always present):
        * email (str)               * contact_id (int)
        - fname (str)               - lname (str)                           
        - prefix (str)              - suffix (str)
        - business (str)            - address1 (str)
        - address2 (str)            - city (str)
        - state (str)               - zip (str)
        - phone (str)               - fax (str)              
        - custom_fields_href (str)  - subscriptions_href (str)
        """
        xml = self.__do_request('contact/%s' % contact_id)

        contact = xml.find('contact')
        return dict(
            contact_id=int(contact.get('id')), \
            fname=contact.find('fname').text, \
            lname=contact.find('lname').text, \
            email=contact.find('email').text, \
            prefix=contact.find('prefix').text, \
            suffix=contact.find('suffix').text, \
            business=contact.find('business').text, \
            address1=contact.find('address1').text, \
            address2=contact.find('address2').text, \
            city=contact.find('city').text, \
            state=contact.find('state').text, \
            zip=contact.find('zip').text, \
            phone=contact.find('phone').text, \
            fax=contact.find('fax').text, \
            custom_fields_href=contact.find('custom_fields').get('{%s}href' % self.NAMESPACE), \
            subscriptions_href=contact.find('subscriptions').get('{%s}href' % self.NAMESPACE))

    def add_update_contact(self, contact_details):
        """
        Adds a contact to iContact, or updates the details for an existing contact.
        Provide the contact's details as a dictionary and the corresponding detail
        items will be added or updated. If 'contact_id' is provided, this method
        updates an existing contact, otherwise it creates a new contact. 
        In both cases the method returns a tuple containing the contact's id 
        (which may be new if the contact was created) and href path.
        
        Here are the key names that you can provide in the dictionary (* items --
        i.e. email -- are always required):        
        - contact_id (int)          - fname (str)         
        - lname (str)               * email (str)        
        - prefix (str)              - suffix (str)
        - business (str)            - address1 (str)
        - address2 (str)            - city (str)
        - state (str)               - zip (str)
        - phone (str)               - fax (str)              
        - custom_fields_href (str)  - subscriptions_href (str)
        
        Example usage::
          # Create a new contact
          client.add_update_contact(dict(email='newemail@address.com', prefix='Mr', lname='Jones'))
        
          # Update an existing contact's email address
          contact = client.contact(1234)        
          contact['email'] = 'updateemail@address.com'
          client.add_update_contact(contact)        
        """
        call_path = 'contact'
        
        if contact_details.get('contact_id', ''):
            # We are updating an existing contact, not adding a new one.
            call_path += '/%s' % contact_details['contact_id']
            contact_id = contact_details['contact_id']
        else:
            contact_id = None
        
        # Build an XML document to represent contact's details.
        contact = Element("contact")
        if contact_id:
            contact.attrib['id'] = str(contact_id)
        def maybe_add_node(detail_name):
            if detail_name in contact_details:
                s = SubElement(contact, detail_name)
                s.text = contact_details[detail_name]
        maybe_add_node('fname')    
        maybe_add_node('lname')    
        maybe_add_node('email')    
        maybe_add_node('prefix')    
        maybe_add_node('suffix')    
        maybe_add_node('business')    
        maybe_add_node('address1')    
        maybe_add_node('address2')    
        maybe_add_node('city')    
        maybe_add_node('state')    
        maybe_add_node('zip')    
        maybe_add_node('phone')    
        maybe_add_node('fax')    
                
        xml = self.__do_request(call_path, {'api_put': ElementTree.tostring(contact)})
        contact = xml.find('result/contact')
        return (int(contact.get('id')), contact.get('{%s}href' % self.NAMESPACE))
        
    def contact_change_subscription(self, contact_id, list_id, subscribed):
        """
        Subscribe or unsubscribe a Contact from a List. If the `subscribed` 
        parameter is True, the contact will be subscribed to the given list, 
        otherwise the contact will be unsubscribed from the list.
        """
        # Build an XML document to represent the contact's subscription status
        call_path = 'contact/%s/subscription/%s' % (contact_id, list_id)
        root = Element("subscription")
        root.attrib['id'] = str(list_id)
        s = SubElement(root, "status")
        s.text = subscribed and 'subscribed' or 'unsubscribed'

        xml = self.__do_request(call_path, {'api_put': ElementTree.tostring(root)})
        subscription = xml.find('result/subscription')
        return (int(subscription.get('id')), subscription.get('{%s}href' % self.NAMESPACE))        
        
    def contact_custom_fields(self, contact_id):
        """
        Returns a list of a contact's custom fields, if any, where each 
        field is represented as a dictionary with the following keys:
        - name (str)                - public_name (str)
        - type (str)                - value (str)
        """
        xml = self.__do_request('contact/%s/custom_fields' % contact_id)

        fields = []
        for field in xml.findall('contact/custom_fields/custom_field'):
            fields.append(dict(name=field.get('name'), \
                public_name=field.get('formal_name'), \
                type=field.get('type'), \
                value=field.find('value').text))
        return fields

    def contact_subscriptions(self, contact_id, list_id=None):
        """
        Returns a list of a contact's subscriptions and current status, 
        where each item in the list is a dictionary with the following keys:
        - id (int)  - subscribed (Boolean)    - status (str)
            
        If you provide the optional `list_id` parameter, the method will
        only retrieve details about that specific list subscription.
        """
        call_path = 'contact/%s/subscriptions' % contact_id
        if list_id:
            call_path += '/%s' % list_id
        xml = self.__do_request(call_path)

        subs = []
        for sub in xml.findall('contact/subscription'):
            subs.append(dict( \
                id=int(sub.get('id')), \
                status=sub.find('status').text, \
                subscribed=sub.find('status').text == 'subscribed'))
        return subs

    def message(self, message_id):
        """
        Returns the details of a message:s
        - id (int)            - subject (str)    - campaign_id (int)
        - created_date (str)  - type (str)       - status (str)
        - body_html (str)     - body_text (str)
            
        NOTE: This API method is not documented in the official iContact
        API documentation, but it works...
        """
        xml = self.__do_request('message/%s' % message_id)
        message = xml.find('message')
        return dict(
            id=int(message.get('id')),
            subject=message.find('subject').text,
            campaign_id=int(message.find('campaign').text),
            created_date=parse(message.find('created').text),
            type=message.find('type').text,
            status=message.find('status').text,
            body_html=message.find('html_body').text,
            body_text=message.find('text_body').text,
        )

    def create_message(self, campaign_id, subject, body_html, body_text):
        """
        Create a new message associated with the given campaign. This method
        creates a message in iContact and returns a tuple containing the 
        message's identifier (int) and href. 
        
        This method does *not* send the message or associate it with any lists,
        use the `schedule_message` method to do this.

        Example usage::        
          # Create a new message in campaign 123
          message = client.create_message(campaign_id=123,
              subject='Message subject', body_html='<h1>Message body</h1>', 
              body_text="Message body")
          message_id = message[0]
        """
        # Build an XML document to represent the new message
        root = Element("message")
        s = SubElement(root, "subject")
        s.text = subject
        s = SubElement(root, "campaign")
        s.text = str(campaign_id)
        s = SubElement(root, "text_body")
        s.text = body_text
        s = SubElement(root, "html_body")
        s.text = body_html

        xml = self.__do_request('message', {'api_put': ElementTree.tostring(root)})
        
        message = xml.find('result/message')
        return (int(message.get('id')), message.get('{%s}href' % self.NAMESPACE))
        
    def schedule_message(self, message_id, list_ids, utc_datetime, archive=True):
        """
        Schedule an existing message to be sent to one or more iContact lists at
        a given time. The scheduled time 'utc_datetime' parameter *must* be given
        in UTC format or the scheduled send time will be wrong. If the 'archive'
        parameter is True the message will be archived (though I don't think 
        archiving is actually set up for any OA lists?)
                
        You can only schedule a message once. To review the scheduled time for a
        message, or to change its schedule, you will need to go to the iContact
        web interface.        
        
        Example usage::
          # Schedule a message (123) to be sent to lists 456 and 789 in 1 minute
          send_datetime_utc = datetime.utcnow() + relativedelta(minutes=1)
          client.schedule_message(message_id=123, list_ids=[456,789], 
              archive=True, utc_datetime=send_datetime_utc)                
        """
        try: 
            iter(list_ids)
        except TypeError: 
            # Someone probably provided a single id, fix it.
            list_ids = [list_ids]
        
        # If provided datetime is not timezone-aware, modify it to be in the 
        # UTC timezone with a zero offset
        if utc_datetime.tzinfo == None:
            utc_datetime = utc_datetime.replace(tzinfo=FixedOffset(0))
        
        # Calculate corresponding time for iContact's servers (UTC -04:00)
        ic_datetime = utc_datetime.astimezone(FixedOffset(-4 * 60))
        
        # Build an XML document to represent the message sending schedule
        root = Element("message")
        root.attrib['id'] = str(message_id)
        sending_info = SubElement(root, "sending_info")
        sending_info.attrib['time'] = ic_datetime.strftime('%a, %d %b %Y %H:%M:%S %z')
        channels = SubElement(sending_info, "channels")
        channels.attrib['archive'] = str(archive).lower()
        channels.attrib['category'] = 'hidden' # What does the category mean? Do we need to care?
        for id in list_ids:
            s = SubElement(channels, "list")
            s.attrib['id'] = str(id)
        # We could add "segment" nodes here, if we need these?
        # We could add "feed" nodes here, if we need these?
        
        call_path = 'message/%s/sending_info' % message_id
        xml = self.__do_request(call_path, {'api_put': ElementTree.tostring(root)})        
        return (message_id, xml.find('results').get('{%s}href' % self.NAMESPACE))
        
    def message_delivery_details(self, message_id):
        """
        Returns the delivery details of a message that has been sent, with
        similar information to that returned by the 'message_stats' method.
        This method returns the following details:
        - id (int)            
        - href (str)
        - channels (list) - We only look for List items, not Feeds or Segments.
          - list id (int)
          - list href (str)
          - list name (str)
          - recipient count (int)
        - stats (dict)
          - bounces: count, percent, href
          - unsubscribed: count, percent, href
          - opens: count, unique, percent, href
          - clicks: count, uniaue, percent, href
          - forwards: count, percent, href
          - released: count, percent
          - comments: count, percent
          - complaints: count, percent

        NOTE: This API method is not documented in the official iContact
        API documentation, but it works...
        """
        xml = self.__do_request('message/%s/sending_info/summary' % message_id)
        
        stats_node = xml.find('message/sending_info/stats')
        results = self.__parse_stats(stats_node)
        
        channels = []
        for c in xml.findall('.//channels'):
            for l in c.findall('list'):
                channels.append(dict(
                    type='list', id=int(l.get('id')), 
                    href=l.get('{%s}href' % self.NAMESPACE),
                    name=l.find('name').text, 
                    count=int(l.find('count').text)
                ))                
            # We could handle "segment" nodes here, do we need these?
            # We could handle "feed" nodes here, do we need these?                
        results['channels'] = channels
        return results

    def message_stats(self, message_id, kind=None):
        """
        Returns statistics for a Message that was sent by iContact, including
        the following kinds: opens, clicks, bounces, unsubscribes, 
        forwards. There is also additional information included in the summary: 
        released, comments, and complaints - these are different from the 
        'kind' statistics because you cannot retrieve the corresponding 
        contact list.
        
        If no `kind` parameter is provided, all the statistics are returned
        but there is no information about which contacts performed the various
        action types.
        
        If a `kind` parameter is provided, all the summary statistics are
        returned in the same way, but the result will include a list of the
        contacts who performed that action in the 'contacts' dictionary field.
        
        For example, to list the summary statistics for message 1234::
          client.message_stats(204715)
        
        To retrieve the list of contacts who clicked links in message 1234::
          client.message_stats(204715, 'clicks')['contacts']                
        """
        call_path = 'message/%s/stats' % message_id
        if kind:
            call_path += '/%s' % kind
        xml = self.__do_request(call_path)
        
        stats_node = xml.find('message/stats')
        results = self.__parse_stats(stats_node)        
        return results


class FixedOffset(tzinfo):
    """
    Fixed offset value that extends the `datetime.tzinfo` object to
    calculate a time relative to UTC.
    
    This class is taken directly from the django module 
    `django.utils.tzinfo`
    """
    def __init__(self, offset):
        """
        Represent a time offset from UTC by a given number of minutes.
        
        For example, to represent the iContact timezone (UTC -04:00)::
            
            utc_datetime = datetime.utcnow()
            ic_datetime = utc_datetime.astimezone(FixedOffset(-4 * 60))
        """
        self.__offset = timedelta(minutes=offset)
        self.__name = u"%+03d%02d" % (offset // 60, offset % 60)

    def __repr__(self):
        return self.__name

    def utcoffset(self, dt):
        return self.__offset

    def tzname(self, dt):
        return self.__name

    def dst(self, dt):
        return timedelta(0)


class ExcessiveRetriesException(Exception):
    """
    A standard exception that represents a potentially transient fault 
    where an an iContact API client fails to perform an operation more
    than `self.max_retry_count` times.
    """
    pass


class ClientException(Exception):
    """
    A standard exception that represents an unrecoverable fault
    during an iContact API operation.
    """
    pass


def _test():
    """
    >>> import logging.config
    >>> logging.basicConfig( \
            level=logging.WARNING, \
            format='%(levelname)-5s [%(name)s] %(asctime)s: %(message)s')        
    
    Set your iContact credentials:
    >>> USERNAME = None
    >>> API_KEY = None
    >>> SHARED_SECRET = None
    >>> APP_PASSWORD = None
    
    Create a client object to interact with the iContact API:
    >>> client = IContactClient( \
                    api_key=API_KEY, \
                    shared_secret=SHARED_SECRET, \
                    username=USERNAME, \
                    md5_password=md5.new(APP_PASSWORD).hexdigest())
     
    Force a manual login. This isn't really necessary, as invoking any
    API operation will login automatically if necessary:
    >>> token, sequence = client.login()

    Lookup your iContact Campaigns:
    >>> campaigns = client.campaigns()
    
    Lookup the details of a specific Campaign:
    >>> campaign_id = campaigns[0][0]
    >>> campaign = client.campaign(campaign_id)

    Lookup your iContact Lists:
    >>> ic_lists = client.lists()
    
    Lookup details of a specific List:
    >>> list_id = ic_lists[0][0]
    >>> ic_list = client.list(list_id)
    
    Create a contact:
    >>> contact_id, url = client.add_update_contact( \
            dict(email='john.doe@nowhere.com', fname='John', lname='Doe'))    
        
    Update an existing contact:
    >>> contact = client.contact(contact_id)
    >>> contact['fname'] = 'Jane'
    >>> contact_id, url = client.add_update_contact(contact)

    Search for contacts based on an email address:
    >>> contacts = client.contacts(email='*@nowhere.com')

    Lookup details for a contact:
    >>> contact_id = contacts[0][0]
    >>> contact = client.contact(contact_id)
    >>> custom_fields = client.contact_custom_fields(contact_id)
    
    Lookup a contact's current subscriptions:
    >>> subs = client.contact_subscriptions(contact_id)    
    
    Check whether a contact has a specific subscription:
    >>> sub = client.contact_subscriptions(contact_id, list_id)    

    Subscribe and unsubscribe a contact to a given List:
    >>> sub_list_id, url = client.contact_change_subscription(contact_id, list_id, True)    
    >>> sub_list_id, url = client.contact_change_subscription(contact_id, list_id, False)
    
    Create a new email message:
    >>> message = client.create_message( \
            campaign_id=campaign_id, \
            subject='Test Message', \
            body_html='<h1>Test Message</h1><p>Here is my <em>html</em> body</p>', \
            body_text="Here is my *text* body")

    Schedule a message to be sent in 10 minutes
    (be careful with this test, lest you accidentally spam your contacts!):
    >>> message_id = message[0]
    >>> # client.schedule_message( \
    >>> #    message_id=message_id, \
    >>> #    list_ids=[list_id], \
    >>> #    archive=False, \
    >>> #    utc_datetime=datetime.utcnow() + relativedelta(minutes=1))    

    Lookup content of a message:
    >>> message_lookup = client.message(message_id)
    
    Lookup delivery details and statistics for a message (only possible for 
    sent messages):
    >>> # delivery_details = client.message_delivery_details(message_id)    
    >>> # stats = client.message_stats(message_id, 'opens')
    
    """
    import doctest
    doctest.testmod()    

if __name__=="__main__":
    _test()
