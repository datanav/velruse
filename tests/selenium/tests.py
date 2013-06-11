import json
import os
import unittest

from nose.plugins.skip import SkipTest

from pyramid.paster import get_app

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait

from webtest.http import StopableWSGIServer

from velruse._compat import ConfigParser

config = {}
browser = None  # populated in setUpModule
server = None  # populated in setUpModule

def splitlines(s):
    return filter(None, [c.strip()
                         for x in s.splitlines()
                         for c in x.split(', ')])

def setUpModule():
    global browser, server

    inipath = os.path.abspath(
        os.environ.get('TEST_INI', 'testing.ini'))
    if not os.path.isfile(inipath):
        raise RuntimeError(
            'Cannot find INI file to setup selenium tests. '
            'Please specify the path via the TEST_INI environment variable '
            'or by adding a testing.ini file to the current directory.')

    parser = ConfigParser()
    parser.read(inipath)

    config.update(parser.items('testconfig'))
    config['test_providers'] = splitlines(config['test_providers'])

    app = get_app(inipath)
    port = int(config['app_port'])
    server = StopableWSGIServer.create(app, port=port)

    driver = config.get('selenium.driver', 'firefox')
    browser = {
        'firefox': webdriver.Firefox,
        'chrome': webdriver.Chrome,
        'ie': webdriver.Ie,
    }[driver]()

def tearDownModule():
    if browser is not None:
        browser.quit()
    if server is not None:
        server.shutdown()

class ProviderTests(object):

    @classmethod
    def require_provider(cls, name):
        if name not in config.get('test_providers', []):
            raise SkipTest('tests not enabled for "%s"' % name)

    def setUp(self):
        browser.delete_all_cookies()

def find_login_url(config, key):
    return config.get(key, config['default_login_url'])

class TestFacebook(ProviderTests, unittest.TestCase):
    """
    TODO: look into adding multiple tests using test users with varying
          levels of functionality.

          http://developers.facebook.com/docs/test_users/
    """

    @classmethod
    def setUpClass(cls):
        cls.require_provider('facebook')
        cls.login = config['facebook.login']
        cls.password = config['facebook.password']
        cls.app = config['facebook.app']
        cls.login_url = find_login_url(config, 'facebook.login_url')

    def test_it(self):
        browser.get(self.login_url)
        self.assertEqual(browser.title, 'Auth Page')
        browser.find_element_by_id('facebook').submit()
        self.assertTrue('Facebook' in browser.title)
        form = browser.find_element_by_id('login_form')
        login = form.find_element_by_name('email')
        login.send_keys(self.login)
        passwd = form.find_element_by_name('pass')
        passwd.send_keys(self.password)
        self.assertTrue(self.app in form.text)
        form.submit()
        WebDriverWait(browser, 10).until(
            lambda driver: driver.find_element_by_id('result'))
        self.assertEqual(browser.title, 'Result Page')
        result = browser.find_element_by_id('result').text
        result = json.loads(result)
        self.assertTrue('profile' in result)
        self.assertTrue('credentials' in result)
        self.assertTrue('displayName' in result['profile'])
        self.assertTrue('verifiedEmail' in result['profile'])
        self.assertTrue('accounts' in result['profile'])

class TestGithub(ProviderTests, unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.require_provider('github')
        cls.login = config['github.login']
        cls.password = config['github.password']
        cls.app = config['github.app']
        cls.login_url = find_login_url(config, 'github.login_url')

    def test_it(self):
        browser.get(self.login_url)
        self.assertEqual(browser.title, 'Auth Page')
        browser.find_element_by_id('github').submit()
        self.assertEqual(browser.title,
                         b'Sign in \xc2\xb7 GitHub'.decode('utf-8'))
        form = browser.find_element_by_id('login')
        login = form.find_element_by_name('login')
        login.send_keys(self.login)
        passwd = form.find_element_by_name('password')
        passwd.send_keys(self.password)
        form.find_element_by_name('commit').submit()
        if browser.title == 'Authorize access to your account':
            WebDriverWait(browser, 10).until(
                lambda driver: driver.find_element_by_name('authorize'))
            btn = browser.find_element_by_name('authorize')
            btn.click()
        WebDriverWait(browser, 10).until(
            lambda driver: driver.find_element_by_id('result'))
        self.assertEqual(browser.title, 'Result Page')
        result = browser.find_element_by_id('result').text
        result = json.loads(result)
        self.assertTrue('profile' in result)
        self.assertTrue('credentials' in result)
        self.assertTrue('displayName' in result['profile'])
        self.assertTrue('accounts' in result['profile'])

class TestTwitter(ProviderTests, unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.require_provider('twitter')
        cls.login = config['twitter.login']
        cls.password = config['twitter.password']
        cls.app = config['twitter.app']
        cls.login_url = find_login_url(config, 'twitter.login_url')

    def test_it(self):
        browser.get(self.login_url)
        self.assertEqual(browser.title, 'Auth Page')
        browser.find_element_by_id('twitter').submit()
        self.assertEqual(browser.title, 'Twitter / Authorize an application')
        app_info = browser.find_elements_by_class_name('app-info')[0]
        self.assertTrue(self.app in app_info.text)
        form = browser.find_element_by_id('oauth_form')
        login = form.find_element_by_id('username_or_email')
        login.send_keys(self.login)
        passwd = form.find_element_by_id('password')
        passwd.send_keys(self.password)
        form.find_element_by_id('allow').submit()
        WebDriverWait(browser, 10).until(
            lambda driver: driver.find_element_by_id('result'))
        self.assertEqual(browser.title, 'Result Page')
        result = browser.find_element_by_id('result').text
        result = json.loads(result)
        self.assertTrue('profile' in result)
        self.assertTrue('credentials' in result)
        self.assertTrue('displayName' in result['profile'])
        self.assertTrue('accounts' in result['profile'])

class TestBitbucket(ProviderTests, unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.require_provider('bitbucket')
        cls.login = config['bitbucket.login']
        cls.password = config['bitbucket.password']
        cls.app = config['bitbucket.app']
        cls.login_url = find_login_url(config, 'bitbucket.login_url')

    def test_it(self):
        browser.get(self.login_url)
        self.assertEqual(browser.title, 'Auth Page')
        browser.find_element_by_id('bitbucket').submit()
        self.assertEqual(browser.title,
                         b'Log in \xe2\x80\x94 Bitbucket'.decode('utf-8'))
        login = browser.find_element_by_id('id_username')
        login.send_keys(self.login)
        passwd = browser.find_element_by_id('id_password')
        passwd.send_keys(self.password)
        passwd.submit()
#        self.assertEqual(browser.title, 'Bitbucket')
#        content = browser.find_element_by_id('content')
#        self.assertTrue(self.app in content.text)
#        form = content.find_element_by_tag_name('form')
#        form.submit()
        WebDriverWait(browser, 10).until(
            lambda driver: driver.find_element_by_id('result'))
        self.assertEqual(browser.title, 'Result Page')
        result = browser.find_element_by_id('result').text
        result = json.loads(result)
        self.assertTrue('profile' in result)
        self.assertTrue('credentials' in result)
        self.assertTrue('displayName' in result['profile'])
        self.assertTrue('accounts' in result['profile'])

class TestGoogle(ProviderTests, unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.require_provider('google')
        cls.login = config['google.login']
        cls.password = config['google.password']
        cls.login_url = find_login_url(config, 'google.login_url')

    def test_it(self):
        browser.get(self.login_url)
        self.assertEqual(browser.title, 'Auth Page')
        browser.find_element_by_id('google').submit()
        WebDriverWait(browser, 10).until(
            lambda driver: driver.find_element_by_id('Email'))
        self.assertEqual(browser.title, 'Google Accounts')
        login = browser.find_element_by_id('Email')
        login.send_keys(self.login)
        passwd = browser.find_element_by_id('Passwd')
        passwd.send_keys(self.password)
        passwd.submit()
        WebDriverWait(browser, 10).until(
            lambda driver: driver.find_element_by_id('result'))
        self.assertEqual(browser.title, 'Result Page')
        result = browser.find_element_by_id('result').text
        result = json.loads(result)
        self.assertTrue('profile' in result)
        self.assertTrue('credentials' in result)
        self.assertTrue('displayName' in result['profile'])
        self.assertTrue('accounts' in result['profile'])

class TestYahoo(ProviderTests, unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.require_provider('yahoo')
        cls.login = config['yahoo.login']
        cls.password = config['yahoo.password']
        cls.login_url = find_login_url(config, 'yahoo.login_url')

    def test_it(self):
        browser.get(self.login_url)
        self.assertEqual(browser.title, 'Auth Page')
        browser.find_element_by_id('yahoo').submit()
        WebDriverWait(browser, 10).until(
            lambda driver: driver.find_element_by_id('username'))
        self.assertEqual(browser.title, 'Sign in to Yahoo!')
        login = browser.find_element_by_id('username')
        login.send_keys(self.login)
        passwd = browser.find_element_by_id('passwd')
        passwd.send_keys(self.password)
        passwd.submit()
        def _wait_for_alert(driver):
            alert = browser.switch_to_alert()
            try:
                alert.accept()
            except:
                pass
            return driver.find_element_by_id('result')
        WebDriverWait(browser, 10).until(_wait_for_alert)
        self.assertEqual(browser.title, 'Result Page')
        result = browser.find_element_by_id('result').text
        result = json.loads(result)
        self.assertTrue('profile' in result)
        self.assertTrue('credentials' in result)
        self.assertTrue('displayName' in result['profile'])
        self.assertTrue('accounts' in result['profile'])

class TestWindowsLive(ProviderTests, unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.require_provider('live')
        cls.login = config['live.login']
        cls.password = config['live.password']
        cls.login_url = find_login_url(config, 'live.login_url')

    def test_it(self):
        browser.get(self.login_url)
        self.assertEqual(browser.title, 'Auth Page')
        browser.find_element_by_id('live').submit()
        WebDriverWait(browser, 10).until(
            lambda driver: driver.find_element_by_name('login'))
        self.assertEqual(browser.title, 'Welcome to Windows Live')
        login = browser.find_element_by_name('login')
        login.send_keys(self.login)
        passwd = browser.find_element_by_name('passwd')
        passwd.send_keys(self.password)
        passwd.submit()
        WebDriverWait(browser, 10).until(
            lambda driver: driver.find_element_by_id('result'))
        self.assertEqual(browser.title, 'Result Page')
        result = browser.find_element_by_id('result').text
        result = json.loads(result)
        self.assertTrue('profile' in result)
        self.assertTrue('credentials' in result)
        self.assertTrue('displayName' in result['profile'])
        self.assertTrue('accounts' in result['profile'])
