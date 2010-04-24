import unittest
from icontact.client import IContactClient
from icontact.tests import settings
import datetime

class ClientTestCase(unittest.TestCase):

    def get_client(self):
        client = IContactClient(settings.ICONTACT_API_KEY, settings.ICONTACT_USERNAME,
                           settings.ICONTACT_PASSWORD)
        return client

    def setUp(self):
        IContactClient.ICONTACT_API_URL = IContactClient.ICONTACT_SANDBOX_API_URL


    def test_account(self):
        s = self.get_client()
        account = s.account()
        self.assertTrue(not account is None, "Did not get account object")
        self.assertTrue(long(account.accountId) > 0, "Did not get valid accountId")

    def test_folder(self):
        s = IContactClient(settings.ICONTACT_API_KEY, settings.ICONTACT_USERNAME,
                           settings.ICONTACT_PASSWORD)
        account = s.account()
        folder = s.clientfolder(account.accountId)
        self.assertTrue(not folder.clientFolderId is None, "Did not get clientFolderId")

    def test_find_or_create_contact(self):
        s = IContactClient(settings.ICONTACT_API_KEY, settings.ICONTACT_USERNAME,
                           settings.ICONTACT_PASSWORD)
        email = 'name@example.com'
        contacts = s.search_contacts({'email':email})
        if contacts.total == 0:
            contacts = s.create_contact(email, firstName='Firstname', lastName='Lastname')
            self.assertTrue(contacts.contacts[0].email == email, "Contacts=%s" % (contacts,))
        else:
            self.assertTrue(contacts.contacts[0].email == email)

    def test_subscribe(self):
        s = IContactClient(settings.ICONTACT_API_KEY, settings.ICONTACT_USERNAME,
                           settings.ICONTACT_PASSWORD)
        email = 'name@example.com'
        contacts = s.search_contacts({'email':email})
        contact_id = contacts.contacts[0].contactId
        result = s.create_subscription(contact_id, settings.ICONTACT_MAIN_LIST_ID)
        self.assertTrue(len(result.subscriptions) == 1)
                                      

    def test_unsubscribe(self):
        # note, you can't unsubscribe, you can only move them to a holding list
        s = IContactClient(settings.ICONTACT_API_KEY, settings.ICONTACT_USERNAME,
                           settings.ICONTACT_PASSWORD)
        email = 'name@example.com'
        contacts = s.search_contacts({'email':email})
        contact_id = contacts.contacts[0].contactId
        result = s.move_subscriber(settings.ICONTACT_MAIN_LIST_ID, contact_id, settings.ICONTACT_HOLDING_LIST_ID)
        self.assertTrue(result.subscription.listId == settings.ICONTACT_HOLDING_LIST_ID)

    def test_create_list(self):
        name = "test_list_%s" % (datetime.datetime.now(),)
        client = self.get_client()
        subject = 'Welcome for %s' % (name,)
        textBody = 'Welcome to list %s' % (name,)
        # TODO: need campaign_id
        #campaign_id = 
        #message_id = client.create_message(subject, 'welcome', textBody=textBody, campaignId=campaign_id)


if __name__ == '__main__':
    unittest.main()

