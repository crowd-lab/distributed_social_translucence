from glob import glob
from shutil import copy2
import csv

files = glob('./*.png')
source_path = '/Users/jts/get_ira_fb_ads/site/images/{}'
dest_path = '/Users/jts/distributed_social_translucence/static/images/exp_images/for_labelling/'
csv_path = '{}labels.csv'.format(dest_path)
with open(csv_path, 'w') as outfile:
    writer = csv.writer(outfile, delimiter=',')
    writer.writerow(['filename', 'guidelines'])
    for path in files:
        name = path.split('_')[1]
        source = source_path.format(name)
        copy2(source, dest_path)
        writer.writerow([name, ''])