import os

class Recordings():
	def update(directory, domain):
		files = [f for f in os.listdir('.') if os.path.isfile(f) and ".py" not in f]
		for f in files:
			with open(f) as file:
				content = file.read().replace("localhost", domain)
			path = "../" + directory + "/" +  f
			with open(path, "w") as file:
				file.write(content)

if __name__ == "__main__":
	Recordings.update("localhost", "localhost")
	Recordings.update("pairwise_dev", "pairwise-dev.cs.vt.edu")
	Recordings.update("heroku", "contentmoderationproject.herokuapp.com")