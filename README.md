# distributed_social_translucence

Testing Setup
-------------

Control Group:
1. Dashboard - localhost:5000/dashboard
2. Wait - localhost:5000/wait?turkId=test1&j=mod&s=wa1&c=con
3. Work - localhost:5000/?turkId=test1

Experimental Group:
1. Dashboard - localhost:5000/dashboard
2. Wait Observer - localhost:5000/wait?turkId=exp1&j=obs&s=wa1&c=exp
3. Wait Moderator (new session, incognito window) - localhost:5000/wait?turkId=exp2&j=mod&s=wa2&c=exp
4. Work Observer - localhost:5000/?turkId=exp1&j=obs&s=wa1
5. Work Moderator - localhost:5000/?turkId=exp2&j=mod&s=wa2

Continuing Experimental:
1. Add new observer - localhost:5000/wait?turkId=exp3&j=obs&s=wa1&c=exp
2. Work new observer - localhost:5000/?turkId=exp3&j=obs&s=wa1
3. Work new moderator - localhost:5000/?turkId=exp1&j=mod&s=wa2

Black Box Images
----------------
- c_441.png
- c_462.png
- c_533.png
- c_1931.png
- c_1941.png
- c_1944.png
- c_2777.png
- l_887.png
- l_1429.png
- l_1440.png
- l_1464.png
- l_1868.png
- l_2859.png