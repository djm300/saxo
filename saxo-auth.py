import requests
import base64
import hashlib
import os

class OAuth2Client:
    def __init__(self, client_id, client_secret, redirect_uri, auth_endpoint, token_endpoint, redirect_uri=None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.auth_endpoint = auth_endpoint
        self.token_endpoint = token_endpoint
	self.redirect_uri = redirect_uri

    def _get_auth_url(self, **params):
        default_params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri
        }
        default_params.update(params)
        return self.auth_endpoint + '?' + '&'.join(f"{k}={v}" for k, v in default_params.items())

    def _exchange_for_token(self, code, code_verifier):
        response = requests.post(self.token_endpoint, data={
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': self.redirect_uri,
            'code_verifier': code_verifier
        })
        print("Token endpoint response status code:", response.status_code)
        print("Token endpoint response content:", response.content)
        return response.json()


def handle_oauth_errors(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            return {"error": str(e)}
    return wrapper

class AuthorizationCodeClient(OAuth2Client):
    def __init__(self, client_id, client_secret, redirect_uri, auth_endpoint, token_endpoint):
        super().__init__(client_id, client_secret, redirect_uri, auth_endpoint, token_endpoint)
        self.code_verifier = None
        self.code_challenge = None

    def _generate_code_verifier(self):
        code_verifier = base64.urlsafe_b64encode(os.urandom(32)).decode('utf-8').rstrip('=')
        self.code_verifier = code_verifier
        return code_verifier

    def _generate_code_challenge(self, code_verifier):
        code_challenge = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        code_challenge = base64.urlsafe_b64encode(code_challenge).decode('utf-8').rstrip('=')
        self.code_challenge = code_challenge
        return code_challenge

    @handle_oauth_errors
    def get_authorization_url(self, **params):
        code_verifier = self._generate_code_verifier()
        code_challenge = self._generate_code_challenge(code_verifier)
        params['code_challenge'] = code_challenge
        params['code_challenge_method'] = 'S256'
        return self._get_auth_url(response_type='code', **params)

    @handle_oauth_errors
    def get_token(self, code):
        return self._exchange_for_token(code, self.code_verifier)


class ClientCredentialsClient(OAuth2Client):
    @handle_oauth_errors
    def get_token(self):
        response = requests.post(self.token_endpoint, data={
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'client_credentials'
        })
        return response.json()

# Define your OAuth2 client
client = AuthorizationCodeClient(
    client_id="c310e92ffc7c481190119ea98c507a2e",
    client_secret="67f8314ea810459e8ddc725a4cfd5568",
    auth_endpoint="https://sim.logonvalidation.net/authorize",
    token_endpoint="https://sim.logonvalidation.net/token",
    redirect_uri="https://djm300.github.io/saxo/oauth-redirect.html"
)

# Get the authorization URL and redirect the user
auth_url = client.get_authorization_url(scope="required_scope")
print(f"Redirect the user to: {auth_url}")

# After redirect, exchange the code for a token
code = "RECEIVED_CODE"
# The code verifier should be the same that was used to generate the code challenge
# In a real application, you would store the code_verifier after generating the authorization URL
# and retrieve it here. For this example, we'll simulate retrieving it from storage.
# code_verifier = retrieve_code_verifier_from_storage()
# For demonstration purposes, we'll generate a new one (THIS IS NOT SECURE IN A REAL APP):
client._generate_code_verifier()
token_info = client.get_token(code)
print(token_info)
