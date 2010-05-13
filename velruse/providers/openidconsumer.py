import logging
import re

from openid.consumer import consumer
from openid.extensions import ax
from openid.extensions import sreg
from openid.oidutil import autoSubmitHTML
from routes import Mapper
from webob import Response
import webob.exc as exc

import velruse.utils as utils

log = logging.getLogger(__name__)

__all__ = ['OpenIDResponder']


# Setup our attribute objects that we'll be requesting
ax_attributes = dict(
    nickname = 'http://axschema.org/namePerson/friendly',
    email = 'http://axschema.org/contact/email',
    full_name = 'http://axschema.org/namePerson',
    birthday = 'http://axschema.org/birthDate',
    gender = 'http://axschema.org/person/gender',
    postal_code = 'http://axschema.org/contact/postalCode/home',
    country = 'http://axschema.org/contact/country/home',
    timezone = 'http://axschema.org/pref/timezone',
    language = 'http://axschema.org/pref/language',
    name_prefix = 'http://axschema.org/namePerson/prefix',
    first_name = 'http://axschema.org/namePerson/first',
    last_name = 'http://axschema.org/namePerson/last',
    middle_name = 'http://axschema.org/namePerson/middle',
    name_suffix = 'http://axschema.org/namePerson/suffix',
    web = 'http://axschema.org/contact/web/default',
)

# Translation dict for AX attrib names to sreg equiv
trans_dict = dict(
    full_name = 'fullname',
    birthday = 'dob',
    postal_code = 'postcode',
)

class AttribAccess(object):
    def __init__(self, sreg_resp, ax_resp):
        self.sreg_resp = sreg_resp or {}
        self.ax_resp = ax_resp or ax.AXKeyValueMessage()
    
    def get(self, key, ax_only=False):
        # First attempt to fetch it from AX
        v = self.ax_resp.getSingle(ax_attributes[key])
        if v:
            return v
        if ax_only:
            return None
        
        # Translate the key if needed
        if key in trans_dict:
            key = trans_dict[key]
        
        # Don't attempt to fetch keys that aren't valid sreg fields
        if key not in sreg.data_fields:
            return None
        
        return self.sreg_resp.get(key)


def extract_openid_data(identifier, sreg_resp, ax_resp):
    """Extract the OpenID Data from Simple Reg and AX data
    
    This normalizes the data to the appropriate format.
    
    """
    attribs = AttribAccess(sreg_resp, ax_resp)
    
    ud = {'identifier': identifier}
    if 'google.com' in identifier:
        ud['providerName'] = 'Google'
    elif 'yahoo.com' in identifier:
        ud['providerName'] = 'Yahoo'
    else:
        ud['providerName'] = 'OpenID'
    
    # Sort out the display name and preferred username
    if ud['providerName'] == 'Google':
        # Extract the first bit as the username since Google doesn't return
        # any usable nickname info
        email = attribs.get('email')
        ud['preferredUsername'] = re.match('(^.*?)@', email).groups()[0]
    else:
        ud['preferredUsername'] = attribs.get('nickname')
    
    # We trust that Google and Yahoo both verify their email addresses
    if ud['providerName'] in ['Google', 'Yahoo']:
        ud['verifiedEmail'] = attribs.get('email', ax_only=True)
    
    # Parse through the name parts, assign the properly if present
    name = {}
    name_keys = ['name_prefix', 'first_name', 'middle_name', 'last_name', 'name_suffix']
    pcard_map = {'first_name': 'givenName', 'middle_name': 'middleName', 'last_name': 'familyName',
                 'name_prefix': 'honorificPrefix', 'name_suffix': 'honorificSuffix'}
    full_name_vals = []
    for part in name_keys:
        val = attribs.get(part)
        if val:
            full_name_vals.append(val)
            name[pcard_map[part]] = val
    full_name = ' '.join(full_name_vals).strip()
    if not full_name:
        full_name = attribs.get('full_name')

    name['formatted'] = full_name
    ud['name'] = name
    
    ud['displayName'] = full_name or ud.get('preferredUsername')
    
    urls = attribs.get('web')
    if urls:
        ud['urls'] = [urls]
    
    for k in ['gender', 'birthday']:
        ud[k] = attribs.get(k)
    
    # Now strip out empty values
    for k, v in ud.items():
        if not v:
            del ud[k]
    
    return ud


class OpenIDResponder(utils.RouteResponder):
    """OpenID Consumer for handling OpenID authentication
    
    This follows the same responder style of Marco apps. It is called
    with a WebOb Request, and responds with a WebOb Response.
    
    """
    map = Mapper()
    map.connect('login', '/auth', action='login', requirements=dict(method='POST'))
    map.connect('process', '/process', action='process')
    
    def __init__(self, storage, openid_store, endpoint_regex, realm):
        """Create the OpenID Consumer"""
        self.storage = storage
        self.openid_store = openid_store
        self.realm = realm
        self.endpoint_regex = endpoint_regex
        self.log_debug = logging.DEBUG >= log.getEffectiveLevel()
    
    @classmethod
    def parse_config(cls, config):
        params = {}
        key_map = {'Realm': 'realm', 'Endpoint Regex': 'endpoint_regex'}
        oids_vals = config['OpenID']
        for k, v in key_map.items():
            if k in oids_vals:
                params[v] = oids_vals[k]
        params['openid_store'] = config['OpenID Store']
        params['storage'] = config['UserStore']
        return params
    
    def _lookup_identifier(self, req, identifier):
        """Extension point for inherited classes that want to change or set
        a default identifier"""
        return identifier
    
    def _update_authrequest(self, req, authrequest):
        """Update the authrequest with the default extensions and attributes
        we ask for
        
        This method doesn't need to return anything, since the extensions
        should be added to the authrequest object itself.
        
        """
        # Add on the Attribute Exchange for those that support that            
        ax_request = ax.FetchRequest()
        for attrib in ax_attributes.values():
            ax_request.add(ax.AttrInfo(attrib))
        authrequest.addExtension(ax_request)
        
        # Form the Simple Reg request
        sreg_request = sreg.SRegRequest(
            optional=['nickname', 'email', 'fullname', 'dob', 'gender', 'postcode',
                      'country', 'language', 'timezone'],
        )
        authrequest.addExtension(sreg_request)
        return None
    
    def _get_access_token(self, request_token):
        """Called to exchange a request token for the access token
        
        This method doesn't by default return anything, other OpenID+Oauth
        consumers should override it to do the appropriate lookup for the
        access token, and return the access token.
        
        """
        return None

    def login(self, req):
        log_debug = self.log_debug
        if log_debug:
            log.debug('Handling OpenID login')
        
        # Load default parameters that all Auth Responders take
        end_point = req.POST['end_point']
        openid_url = req.POST.get('openid_identifier')
        
        if not openid_url or not re.match(self.endpoint_regex, end_point):
            return self._error_redirect(0, end_point)
        
        openid_session = {}
        oidconsumer = consumer.Consumer(openid_session, self.openid_store)
        
        # Let inherited consumers alter the openid identifier if desired
        openid_url = self._lookup_identifier(req, openid_url)
        
        try:
            authrequest = oidconsumer.begin(openid_url)
        except consumer.DiscoveryFailure:
            return self._error_redirect(1, end_point)
        
        if authrequest is None:
            return self._error_redirect(1, end_point)
        
        # Update the authrequest
        self._update_authrequest(req, authrequest)
        
        return_to = req.link('process', qualified=True)
        
        # Ensure our session is saved for the id to persist
        req.session['end_point'] = end_point
        req.session.save()
        
        # OpenID 2.0 lets Providers request POST instead of redirect, this
        # checks for such a request.
        if authrequest.shouldSendRedirect():
            redirect_url = authrequest.redirectURL(realm=self.realm, 
                                                   return_to=return_to, 
                                                   immediate=False)
            self.storage.store(req.session.id, openid_session, expires=300)
            return exc.HTTPFound(location=redirect_url)
        else:
            html = authrequest.htmlMarkup(realm=self.realm, return_to=return_to, 
                                          immediate=False)
            self.storage.store(req.session.id, openid_session, expires=300)
            return Response(body=html)
    
    def process(self, req):
        """Handle incoming redirect from OpenID Provider"""
        log_debug = self.log_debug
        if log_debug:
            log.debug('Handling processing of response from server')
        
        end_point = req.session['end_point']
        
        openid_session = self.storage.retrieve(req.session.id)
        if not openid_session:
            return self._error_redirect(1, end_point)
        
        # Setup the consumer and parse the information coming back
        oidconsumer = consumer.Consumer(openid_session, self.openid_store)
        info = oidconsumer.complete(req.params, req.link('process', qualified=True))
        
        if info.status in [consumer.FAILURE, consumer.CANCEL]:
            return self._error_redirect(2, end_point)
        elif info.status == consumer.SUCCESS:
            openid_identity = info.identity_url
            if info.endpoint.canonicalID:
                # If it's an i-name, use the canonicalID as its secure even if
                # the old one is compromised
                openid_identity = info.endpoint.canonicalID
            
            user_data = extract_openid_data(identifier=openid_identity, 
                                            sreg_resp=sreg.SRegResponse.fromSuccessResponse(info),
                                            ax_resp=ax.FetchResponse.fromSuccessResponse(info))
            result_data = {'status': 'ok', 'profile': user_data}
            
            # Did we get any OAuth info?
            oauth = info.extensionResponse('http://specs.openid.net/extensions/oauth/1.0', False)
            if oauth and 'request_token' in oauth:
                access_token = self._get_access_token(oauth['request_token'])
                if access_token:
                    result_data['credentials'] = access_token
            
            # Delete the temporary token data used for the OpenID auth
            self.storage.delete(req.session.id)
            
            # Generate the token, store the extracted user-data for 5 mins, and send back
            token = utils.generate_token()
            self.storage.store(token, result_data, expires=300)
            form_html = utils.redirect_form(req.session['end_point'], token)
            return Response(body=autoSubmitHTML(form_html))
        else:
            return self._error_redirect(1, end_point)
