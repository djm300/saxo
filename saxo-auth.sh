#!/bin/bash
curl -vv \
  -H 'User-Agent: python-requests/2.32.5' \
  -H 'Accept-Encoding: gzip, deflate' \
  -H 'Accept: */*' \
  -H 'Connection: keep-alive' \
  -H 'Content-Length: 288' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'client_id=c310e92ffc7c481190119ea98c507a2e&\
grant_type=authorization_code&\
code=fa4dfead-5792-4c00-8326-313303599200&\
redirect_uri=https%3A%2F%2Fdjm300.github.io%2Fsaxo%2Foauth-redirect.html&\
code_verifier=MwST9eCqNaboHdvBjIcrCbj1clA6vQ5fXdzy1DLiTOQqLrByAn58TiD6pUj5_bxXHANZ9Fp4mkDq9nXkq0CLfQ' \
https://sim.logonvalidation.net/token
