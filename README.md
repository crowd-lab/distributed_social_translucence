# distributed_social_translucence

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
- n_36.png
- n_1689.png
- n_1784.png
- n_1870.png
- n_1871.png
- n_2780.png
- n_3511.png

Known Bugs
----------
- Workers in experimental condition sometimes have same TogetherJS user color (red)
- Dashboard doesn't list unpaired observers in experimental condition
- Dashboard sometimes lists pairs in experimental condition out of order (ordered by pair id)
- TogetherJS sidebar show more than two participants for a few seconds if partner had refreshed on wait page
- First refresh for first moderator worker hides affiliation form, second refresh shows it again
- Strike-throughs don't appear properly in control condition on dashboard
- Worker chain breaks if user disconnects and doesn't reconnect to wait page
- "Server overloading" 500 error when first pair entered work page (issue with first pilot)
- Unpaired moderator not moved to control condition as they should after experiment is marked as complete

Planned Improvements
--------------------
- Workers in experimental condition should be notified when their partner has finished their task and left the page
- Maximum image/post height constraints for better page scaling
