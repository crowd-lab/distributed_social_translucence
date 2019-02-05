import csv
import os
import re

IMAGE_DIR = 'static/images/'

def extract_images(x):
    name = re.search(re.compile('\d+'), x).group(0)
    affiliation = re.search(re.compile('^\w'), x).group(0)
    return (name, {'affiliation': affiliation, 'path': IMAGE_DIR + x})

files = os.listdir(IMAGE_DIR)
interim = [extract_images(x) for x in files]
final_data = {k: v for (k,v) in interim}

with open('../get_ira_fb_ads/site/index.csv', 'r') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        if row['id'] in final_data.keys():
            final_data[row['id']]['text'] = row['description']
            final_data[row['id']]['poster'] = ''
            

with open('./images_table.csv', 'w') as f:
    fieldnames = ['path', 'text', 'poster', 'affiliation']
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    for name, data in final_data.items():
        writer.writerow(data)