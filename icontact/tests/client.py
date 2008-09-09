# Copyright 2008 Online Agility (www.onlineagility.com)
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
r"""
>>> import md5
>>> from datetime import datetime
>>> from dateutil.relativedelta import relativedelta
>>> from icontact.client import IContactClient

# Set your iContact credentials:
>>> USERNAME = None
>>> API_KEY = None
>>> SHARED_SECRET = None
>>> APP_PASSWORD = None

# Create a client object to interact with the iContact API:
>>> client = IContactClient(api_key=API_KEY, shared_secret=SHARED_SECRET, \
...                         username=USERNAME, md5_password=md5.new(APP_PASSWORD).hexdigest())

# Force a manual login. This isn't really necessary, as invoking any
# API operation will login automatically if necessary:
>>> token, sequence = client.login()

# Lookup your iContact Campaigns:
>>> campaigns = client.campaigns()

# Lookup the details of a specific Campaign:
>>> campaign_id = campaigns[0][0]
>>> campaign = client.campaign(campaign_id)

# Lookup your iContact Lists:
>>> ic_lists = client.lists()
    
# Lookup details of a specific List:
>>> list_id = ic_lists[0][0]
>>> ic_list = client.list(list_id)
    
# Create a contact:
>>> contact_id, url = client.add_update_contact(dict(email='john.doe@nowhere.com', fname='John', lname='Doe'))    
        
# Update an existing contact:
>>> contact = client.contact(contact_id)
>>> contact['fname'] = 'Jane'
>>> contact_id, url = client.add_update_contact(contact)

# Search for contacts based on an email address:
>>> contacts = client.contacts(email='*@nowhere.com')

# Lookup details for a contact:
>>> contact_id = contacts[0][0]
>>> contact = client.contact(contact_id)
>>> custom_fields = client.contact_custom_fields(contact_id)
    
# Lookup a contact's current subscriptions:
>>> subs = client.contact_subscriptions(contact_id)    
    
# Check whether a contact has a specific subscription:
>>> sub = client.contact_subscriptions(contact_id, list_id)    

# Subscribe and unsubscribe a contact to a given List:
>>> sub_list_id, url = client.contact_change_subscription(contact_id, list_id, True)    
>>> sub_list_id, url = client.contact_change_subscription(contact_id, list_id, False)
    
# Create a new email message:
>>> message = client.create_message(campaign_id=campaign_id, subject='Test Message', \
...                                 body_html='<h1>Test Message</h1><p>Here is my <em>html</em> body</p>', \
...                                 body_text="Here is my *text* body")

# Schedule a message to be sent in 10 minutes
# (be careful with this test, lest you accidentally spam your contacts!):
>>> message_id = message[0]

>>> # client.schedule_message(message_id=message_id, \
... #                        list_ids=[list_id], \
... #                         archive=False, \
... #                        utc_datetime=datetime.utcnow() + relativedelta(minutes=1))    

# Lookup content of a message:
>>> message_lookup = client.message(message_id)

# Lookup delivery details and statistics for a message (only possible for 
# sent messages):
>>> # delivery_details = client.message_delivery_details(message_id)    
>>> # stats = client.message_stats(message_id, 'opens')
"""

if __name__=="__main__":
    import doctest
    doctest.testmod()