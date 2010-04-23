import unittest
from icontact.client import IContactClient
from icontact.tests import settings


class ClientTestCase(unittest.TestCase):

    def setUp(self):
        IContactClient.ICONTACT_API_URL = IContactClient.ICONTACT_SANDBOX_API_URL


    def test_account(self):
        s = IContactClient(settings.ICONTACT_API_KEY, settings.ICONTACT_USERNAME,
                           settings.ICONTACT_PASSWORD)
        account = s.account()
        self.assertTrue(not account is None, "Did not get account object")
        self.assertTrue(int(account['accountId']) > 0, "Did not get valid accountId")

    def test_folder(self):
        s = IContactClient(settings.ICONTACT_API_KEY, settings.ICONTACT_USERNAME,
                           settings.ICONTACT_PASSWORD)
        account = s.account()
        folder = s.clientfolder(account['accountId'])
        self.assertTrue(not folder['clientFolderId'] is None, "Did not get clientFolderId")


if __name__ == '__main__':
    unittest.main()

