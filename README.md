# distributed_social_translucence

Testing Setup
-------------

Control Group:
1. Dashboard - localhost:5000/dashboard
2. Wait - localhost:5000/wait?turk=test1&j=mod&s=wa1&c=con
3. Work - localhost:5000/?turk=test1

Experimental Group:
1. Dashboard - localhost:5000/dashboard
2. Wait Observer - localhost:5000/wait?turk=exp1&j=obs&s=wa1&c=exp
3. Wait Moderator (new session) - localhost:5000/wait?turk=exp2&j=mod&s=wa2&c=exp
4. Work Moderator - localhost:5000/?turk=exp2&j=mod&s=wa2
5. Work Observer - localhost:5000/?turk=exp1&j=obs&s=wa1

Continuing Experimental:
1. Add new observer - localhost:5000/wait?turk=exp3&j=obs&s=wa1&c=exp
2. Work new moderator - localhost:5000/?turk=exp1&j=mod&s=wa2
3. Work new observer - localhost:5000/?turk=exp3&j=obs&s=wa1
