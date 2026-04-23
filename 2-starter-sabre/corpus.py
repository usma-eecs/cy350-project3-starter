import hashlib
import os
import glob
import logging

logging.basicConfig(level=logging.INFO)


class Corpus:
    url = "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/gutenberg.zip"
    dest_file = "gutenberg.zip"
    dest_path = "gutenberg"
    expected_hash = "2d3c3ab548c653944310f37f536443ec85d0a0ad855fcae217a0c9efdce2d611"

    def __init__(self, debug=None):
        if debug:
            logging.getLogger().setLevel(logging.DEBUG)
        self.ready = self.download_corpus() and self.unzip_corpus()
        logging.debug(f"Files in corpus: {self.list_files()}")

    def download_corpus(self):
        dest_file = Corpus.dest_file
        dest_path = Corpus.dest_path

        # check if the file already exists
        if os.path.exists(dest_file):
            logging.debug(f"{dest_file} found. Verifying hash...")
            # verify the hash of the existing file
            actual_hash = hashlib.sha256(open(dest_file, "rb").read()).hexdigest()
            if actual_hash == Corpus.expected_hash:
                logging.debug(f"{dest_file} is valid.")
                return True

            logging.debug(f"{dest_file} hash mismatch.")
            os.remove(dest_file)

        logging.debug(f"Downloading corpus...")
        try:
            import urllib.request

            response = urllib.request.urlopen(Corpus.url)
            with open(dest_file, "wb") as f:
                f.write(response.read())

        except Exception as e:
            logging.debug(f"An error occurred while downloading the corpus: {e}")
            return False

        # check sha256 hash of the downloaded file
        actual_hash = hashlib.sha256(open(dest_file, "rb").read()).hexdigest()
        if actual_hash != Corpus.expected_hash:
            logging.debug(f"Hash mismatch for downloaded file.")
            return False

        logging.debug(f"Download complete and verified. Extracting corpus...")

        return True

    def unzip_corpus(self):
        dest_file = Corpus.dest_file
        dest_path = Corpus.dest_path

        if (
            os.path.exists(dest_path)
            and os.path.isdir(dest_path)
            and os.listdir(dest_path)
        ):
            logging.debug(
                f"{dest_path} already exists and is not empty. Skipping unzip."
            )
            return True

        if not os.path.exists(dest_file):
            logging.debug(f"{dest_file} not found. Cannot unzip.")
            return False

        try:
            import zipfile

            with zipfile.ZipFile(dest_file, "r") as zip_ref:
                zip_ref.extractall(".")
            logging.debug(f"Corpus extracted to {dest_path}.")
            return True

        except Exception as e:
            logging.debug(f"An error occurred while extracting the zip file: {e}")
            return False

    def list_files(self):
        if not self.ready:
            raise RuntimeError("Corpus not ready. Cannot list files.")
        files = glob.glob(os.path.join(Corpus.dest_path, "*"))
        if not files:
            raise RuntimeError("No files found in corpus directory.")
        return files

        # return [f for f in os.listdir(Corpus.dest_path) if os.path.isfile(os.path.join(Corpus.dest_path, f))]

    def read_file(self, filepath, read_mode="rb"):
        if filepath not in self.list_files():
            raise FileNotFoundError(f"{filepath} not found in corpus.")

        # read as binary by default to avoid encoding issues
        # to read as text, specify read_mode="r" in function arguments
        with open(filepath, read_mode) as f:
            return f.read()

    def generate_sha256_list(self):

        sha256_dict = {}
        for filepath in self.list_files():
            with open(filepath, "rb") as f:
                file_data = f.read()

            # remove .txt extension and use filename as key
            key = os.path.splitext(os.path.basename(filepath))[0]

            file_hash = hashlib.sha256(file_data).hexdigest()
            sha256_dict[key] = file_hash

        return sha256_dict
