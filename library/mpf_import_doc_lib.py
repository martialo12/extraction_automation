# python standard library
import logging
import os
from pathlib import Path
from typing import Dict, List, Tuple
from zipfile import ZipFile
import smtplib
import platform as pl
import subprocess as sp
import shutil
import xml.etree.ElementTree as ET
import requests
from datetime import datetime
import json
import subprocess
import string
import random
from pathlib import Path
import copy

# Third-party libraries
import yaml
import pexpect
import hashlib
import cryptocode
from time import sleep

logger = logging.getLogger(__name__)


class MpfImportDoclib:
    def __init__(self, config):
        valid_lotto_files = self.check_validation_files(config)
        if len(valid_lotto_files) != 0:
            self.check_values_from_map_and_md5_file(valid_lotto_files, config)
            sleep(20)
            lotto_numbers = self.zip_data(config)
            
            for lotto_number in lotto_numbers:
                
                self.unzip_data(config, lotto_number)
                current_datetime_lotto = self.copy_lotto_data_for_acces_pdf_files(config, lotto_number)
                all_data = self.extract_info_from_xml(config, current_datetime_lotto, lotto_number)
                try:
                    self.send_data_with_api(config, all_data)
                    message = f"Hi, \n we're happy to let you know that lotto {lotto_number} was send successfully."
                    MpfImportDoclib.send_mail_notification_lotto(config, lotto_number, message)
                except Exception as e:
                    logger.error(f"Something went wrong when trying to send lotto {lotto_number} data...:  {e}")
                    message = f"Hi, \n we're sorry to let you know that lotto {lotto_number} was not send successfully."
                    MpfImportDoclib.send_mail_notification_lotto(config, lotto_number, message)
        else:
            logger.error("!!! lotto files are not valid !!!")
            raise Exception("lotto files are not valid!!!")
        
    @classmethod
    def load_configuration(cls) -> Dict:
        config_path = Path(__file__).parent.parent / "config/config.yaml"
        with open(rf'{config_path}') as cfgfile:
            logger.info("loading sftp configuration from config yaml file...")
            config = yaml.load(cfgfile, Loader=yaml.FullLoader)
        return config

    @classmethod
    def sftp_connect_download(cls, config: dict) -> None:
        sftp_config = config["SFTP_CONFIG"]
        logger.debug(f"SFTP CONFIG: \n {sftp_config}")
        hostname = sftp_config['hostname']
        username = sftp_config['username']
        password = sftp_config['password']
        privatekey = sftp_config['privatekey']
        passphrase = sftp_config['passphrase']
        timeout = sftp_config['timeout']
        path_download_to_network_share = sftp_config['path_download_to_network_share']
        
        path_to_download_lotto = path_to_private_key = Path(
            __file__).parent.parent / "download"
        
        # make sure that path_to_download_lotto exists
        Path(path_to_download_lotto).mkdir(parents=True, exist_ok=True)
        
        
        path_to_private_key = Path(
            __file__).parent.parent / f"config/{privatekey}"
        logger.debug(f"path to private key: {path_to_private_key}")

        try:
            logger.info('downloading data from remote SFTP...')

            logger.info(f'downnload data to: {path_download_to_network_share}')

            child = pexpect.spawn(
                f"sftp -i {path_to_private_key} {username}@{hostname}", timeout=timeout)

            child.expect(f"Enter passphrase for key '{path_to_private_key}':")
            child.sendline(f"{passphrase}")

            logger.debug(f"----child before-----: {child.before}")

            child.expect("Enter password:")
            child.sendline(f"{password}")

            logger.debug(f"----child before-----: {child.before}")

            child.expect("sftp>")
            child.sendline(f"get /*.*  {path_download_to_network_share}")
            child.expect("sftp>")
            
            child.sendline(f"get /*.*  {path_to_download_lotto}")
            child.expect("sftp>")

            child.sendline(f"rm /*.*  {path_download_to_network_share}")
            child.expect("sftp>")
            logger.info(
                'WELL DONE ! Successfully download all data fom remote SFTP.')
        except pexpect.TIMEOUT as e:
            logger.warning(
                f"SORRY! timeout expired: {e}")
            MpfImportDoclib.send_mail(config)
        except Exception as e:
            logger.error(f"Something went wrong when trying to connect to  SFTP...:  {e}")
    
    def _extract_all_lotto_numbers(self, config: dict) -> set:
        logger.info("extracting lotto numbers...")
        sftp_config = config["SFTP_CONFIG"]
        path_download_to_network_share = sftp_config['path_download_to_network_share']
        
        parts_files = []
        for filename in os.listdir(path_download_to_network_share):

            if filename.endswith(".t") or filename.endswith(".md5"):
                continue
            else:
                    parts_files.append(filename) 
        logger.debug(f"parts_files: {parts_files}")
        
        all_lotto_numbers = set()
        for part_file in parts_files:
            prefix_part_file = part_file.split(".")[0]
            logger.debug(f"prefix_part_file: {prefix_part_file}")
            lotto_number = prefix_part_file.split("_")[2]
            logger.debug(f"lotto number: {lotto_number}")
            all_lotto_numbers.add(lotto_number)
        
        logger.debug(f"all lotto number: {all_lotto_numbers}")

        return all_lotto_numbers


    def _map_lotto_number_to_files(self, config: dict, lotto_numbers: set) -> Dict[str, List[str]]:
        sftp_config = config["SFTP_CONFIG"]
        path_download_to_network_share = sftp_config['path_download_to_network_share']
        
        lotto_zips = {}

        for lotto_number in lotto_numbers:
            lotto_files = []
            for filename in os.listdir(path_download_to_network_share):
                if filename.endswith(".t") or filename.endswith(".md5"):
                    continue
                else:
                    if filename.find(lotto_number) != -1:
                        lotto_files.append(filename)
            
            lotto_zips[f"{lotto_number}"] = lotto_files
            logger.debug(f"lotto zip files: {lotto_zips}")
        
        return lotto_zips

    
    def zip_data(self, config: dict) -> set:
        sftp_config = config["SFTP_CONFIG"]
        path_download_to_network_share = sftp_config['path_download_to_network_share']

        lotto_numbers = self._extract_all_lotto_numbers(config)
        lotto_zips = self._map_lotto_number_to_files(config, lotto_numbers)
        logger.debug(f"moving lotto files  in lotto number folder....")
        for lotto_number, lotto_files in lotto_zips.items():
            sp.call(f"cd {path_download_to_network_share}", shell=True)
            sp.call(f"mkdir -p {path_download_to_network_share}/{lotto_number}", shell=True)
            for lotto_file in lotto_files:
                sp.call(f"mv {path_download_to_network_share}/{lotto_file} {path_download_to_network_share}/{lotto_number}", shell=True)
        
        for lotto_number, lotto_files in lotto_zips.items():
            path_to_zip_file = f"{path_download_to_network_share}/{lotto_number}"
            Path(path_to_zip_file).mkdir(parents=True, exist_ok=True)
            logger.debug(f"zipping lotto {lotto_number} data...")
            os_command = f"cat {path_download_to_network_share}/{lotto_number}/* > {path_to_zip_file}/{lotto_number}.zip"
            os.system(os_command)
        
        return lotto_numbers


    def unzip_data(self, config: dict, lotto_number: str) -> None:
        logger.info(f"start unzipping data for lotto {lotto_number}...")
        sftp_config = config["SFTP_CONFIG"]
        path_download_to_network_share = sftp_config['path_download_to_network_share']
        path_to_zip_file = path_download_to_network_share + "/" + lotto_number + "/" + lotto_number +".zip"
        directory_to_extract_to = path_download_to_network_share + "/" + lotto_number

        with ZipFile(path_to_zip_file, 'r') as zip_file:
            zip_file.extractall(directory_to_extract_to)

    
    def check_validation_files(self, config) -> List[str]:
        sftp_config = config["SFTP_CONFIG"]
        unzip_lotto_data = sftp_config['path_download_to_network_share']
        valid_lotto_files = []
        all_files = []
        for filename in os.listdir(unzip_lotto_data):
            if os.path.isfile(unzip_lotto_data + "/" +filename):
                all_files.append(filename)
                filname_without_extension = filename.split(".")[0]
                length_file_without_ext = len(filname_without_extension)
                if filename.startswith("Lotto_PwC_") \
                        and length_file_without_ext > len("Lotto_PwC_") \
                        or filename.endswith(".t"):
                    logger.debug(f"filename lotto: {filename}")
                    valid_lotto_files.append(filename)

        all_files_valid = True
        for valid_file in valid_lotto_files:
            if valid_file not in all_files:
                logger.info(f"{valid_file} is not valid")
                all_files_valid = False

        if all_files_valid == True:
            logger.info(f"files {valid_lotto_files} are all valid")
            return valid_lotto_files
        else: 
            return []

    def check_values_from_map_and_md5_file(self, valid_lotto_files: List[str], config:dict) ->None:
        # generate mapping dictionary
        map_files = self._generate_map_from_lotto_files(valid_lotto_files)
        #lotto_files = map_files["files"]

        for map_file in map_files:
            # check that in the map the value (file) corresponding to the md5 key is not null
            assert(map_file["md5"] != None)
            lotto_files = map_file["files"]

            # reads the content of the md5 file, and verifies that the number of files present 
            # in the index corresponds to the number of files present in the map with files key
            number_files = self._check_number_files(config, map_file["md5"])   
            logger.debug(f"number_files: {number_files}")         
            assert(number_files == len(lotto_files))
        
        
            # Checks that the checksum of each file matches the checksum in the .md5 file.
            checksum_files, checksum_files_from_map = self._check_checksum_files(config, map_file["md5"], lotto_files)
            assert(checksum_files == checksum_files_from_map)


    def _md5checksum(self, fname) ->str:

        md5 = hashlib.md5()

        # handle content in binary form
        f = open(fname, "rb")

        while chunk := f.read(4096):
            md5.update(chunk)

        return md5.hexdigest()


    def _generate_map_from_lotto_files(self, valid_lotto_files: List[str]) ->List[Dict[str, List[str]]]:
        # filter files: take everything except files with .t and .md5
        filter_files = []

        for valid_file in valid_lotto_files:
            if valid_file.endswith(".md5") or valid_file.endswith(".t"):
                continue
            else:
                filter_files.append(valid_file)
        
        logger.debug(f"filter files are:  {filter_files} ")

        # count number lotto files
        count = 0
        md5_files = []
        for valid_file in valid_lotto_files:
            if valid_file.endswith(".md5"):
                count += 1
                md5_files.append(valid_file)
        logger.info(f"there are {count} lotto files")
        logger.debug(f"md5 files are:  {md5_files} ")

        map_files = []
        for md5_file in md5_files:
            logger.debug(f"md5 file:  {md5_file} ")
            lotto_files = []
            map_lotto = dict()
            for valid_file in filter_files:
                if valid_file.startswith(md5_file[:-4]):
                    lotto_files.append(valid_file)
                    map_lotto["md5"] = md5_file
                    map_lotto["files"] = lotto_files

            map_files.append(map_lotto)

        logger.debug(f"map files list dictionary: {map_files}")
        # logger.debug(f"length lotto files in map: {len(lotto_files)}")
        return map_files

    def _check_number_files(self, config:dict, md5_filename: str) ->int:
        
        sftp_config = config["SFTP_CONFIG"]
        unzip_lotto_data = sftp_config['path_download_to_network_share']

        number_files = 0
        for filename in os.listdir(unzip_lotto_data):
            if os.path.isfile(unzip_lotto_data + "/" +filename):
                if filename == md5_filename:
                    md5_file = unzip_lotto_data + "/" + filename
                    with open(md5_file) as f:
                        lines = f.readlines()
                        logger.debug(f"{lines}")
                        
                        # extract numberfiles
                        number_files = lines[-1]
                        number_files = number_files.split("\n")[0]
                        number_files = int(number_files.split(" ")[-1])
                        logger.debug(f"number files: {number_files}")
        return number_files

    def _check_checksum_files(self, config:dict, md5_filename: str, lotto_files: List[str]) ->Tuple[list, list]:
        sftp_config = config["SFTP_CONFIG"]
        unzip_lotto_data = sftp_config['path_download_to_network_share']

        checksum_files = []
        checksum_files_from_map = []
        for filename in os.listdir(unzip_lotto_data):
            if os.path.isfile(unzip_lotto_data + "/" +filename):
                if filename == md5_filename:
                    md5_file = unzip_lotto_data + "/" + filename
                    with open(md5_file) as f:
                        lines = f.readlines()
                        logger.debug(f"{lines}")
                        
                        # TODO: bug fixed
                        # extract numberfiles
                        number_files = lines[-1]
                        number_files = number_files.split("\n")[0]
                        number_files = int(number_files.split(" ")[-1])
                        
                        logger.debug(f"number of files todo:{number_files}")
                        for i in range(0, number_files):
                            checksum_file = lines[i]
                            checksum_file = checksum_file.split("*")[0].strip()
                            logger.debug(f"checksum for lotto file 00{i} from map is : {checksum_file}")
                            checksum_files_from_map.append(checksum_file)

                elif filename in lotto_files:
                    # Checks that the checksum of each file matches the checksum in the .md5 file.
                    md5_file = unzip_lotto_data + "/" + filename
                    checksum_key=self._md5checksum(md5_file)
                    logger.debug(f"checksum for '{md5_file}' is : {checksum_key}")
                    checksum_files.append(checksum_key)
                else:
                    continue
        
            
        checksum_files.sort()
        checksum_files_from_map.sort()
        
        return checksum_files, checksum_files_from_map
    
    @classmethod
    def send_mail(cls, config: dict) ->None:
        smtp_config = config["SMTP_CONFIG"]
        logger.debug(f"SMTP CONFIG: \n {smtp_config}")
        fromaddr = smtp_config["fromaddr"]
        toaddrs = list(smtp_config["toaddrs"])
        subject = smtp_config["subject"]
        message = smtp_config["message"]
        host = smtp_config["host"]
        port = smtp_config["port"]
        logger.info(f"sending mail from {fromaddr} to {toaddrs}")
        try:
            header = 'To:' + ' '.join(toaddrs) + '\n' + 'From: ' + fromaddr + '\n'
            msg = header + f'Subject: {subject}\n\n{message}.'
            server = smtplib.SMTP(host, port)
            # server.starttls()
            server.ehlo()
            server.sendmail(fromaddr, toaddrs, msg)
            server.quit()
        except Exception as e:
            logger.error(f"Something went wrong when trying to send mail to {toaddrs}...:  {e}")
    
    @classmethod
    def send_mail_notification_lotto(cls, config: dict, lotto_number: str, message: str) ->None:
        smtp_config = config["SMTP_CONFIG"]
        logger.debug(f"SMTP CONFIG: \n {smtp_config}")
        fromaddr = smtp_config["fromaddr"]
        toaddrs = list(smtp_config["toaddrs"])
        subject = f"Importazione lotto {lotto_number}"
        
        host = smtp_config["host"]
        port = smtp_config["port"]
        logger.info(f"sending notification lotto mail from {fromaddr} to {toaddrs}")
        try:
            header = 'To:' + ' '.join(toaddrs) + '\n' + 'From: ' + fromaddr + '\n'
            msg = header + f'Subject: {subject}\n\n{message}.'
            server = smtplib.SMTP(host, port)
            # server.starttls()
            server.ehlo()
            server.sendmail(fromaddr, toaddrs, msg)
            server.quit()
        except Exception as e:
            logger.error(f"Something went wrong when trying to send mail to {toaddrs}...:  {e}")
    
    
    @classmethod
    def move_data_to_backup(cls, config: dict) ->str:
        sftp_config = config["SFTP_CONFIG"]
        backup_path = sftp_config["path_historic_to_network_share"] 
        unzip_lotto_data = sftp_config["path_download_to_network_share"]
        logger.info(f"moving all files from {unzip_lotto_data} to {backup_path}")
        current_year = datetime.now().year
        current_datetime = datetime.today().strftime('%Y_%m_%d__%H_%M_%S')
        logger.debug(f"CURRENT DATE: {current_datetime}")
        sp.call(f"cd {backup_path}", shell=True)
        sp.call(f"mkdir -p {backup_path}/{current_year}", shell=True)
        sp.call(f"cd {backup_path}/{current_year}", shell=True)
        sp.call(f"mkdir -p {backup_path}/{current_year}/{current_datetime}", shell=True)
        sp.call(f"cd {backup_path}/{current_year}/{current_datetime}", shell=True)
        new_backup_path = backup_path + f"/{current_year}/{current_datetime}/"
        sp.call(f"cp -r {unzip_lotto_data}/* {new_backup_path}", shell=True)
        return str(current_datetime)
        
    
    @classmethod
    def check_downloaded_files(cls, config: dict) -> bool:
        sftp_config = config["SFTP_CONFIG"]
        unzip_lotto_data = sftp_config["path_download_to_network_share"]
        if len(os.listdir(unzip_lotto_data)) == 0:
            logger.info(f"there is currently no files inside {unzip_lotto_data}")
            return False
        logger.info(f"{len(os.listdir(unzip_lotto_data))} was downloaded from remote SFTP")
        return True
        
    
    @classmethod
    def move_data_to_processed(cls, config: dict, current_date: str) -> None:
        sftp_config = config["SFTP_CONFIG"]
        logger.debug(f"SFTP CONFIG: \n {sftp_config}")
        hostname = sftp_config['hostname']
        username = sftp_config['username']
        password = sftp_config['password']
        privatekey = sftp_config['privatekey']
        passphrase = sftp_config['passphrase']
        path_historic_to_network_share = sftp_config['path_historic_to_network_share']
        
        home_path = path_to_private_key = Path(
            __file__).parent.parent
        logger.debug(f"home path: {home_path}")
        
        path_to_download_lotto = path_to_private_key = Path(
            __file__).parent.parent / "download"
        
        path_to_download_zip_lotto = path_to_private_key = Path(
            __file__).parent.parent / f"download/{current_date}"
        
        # make sure that path_to_download_zip_lotto exists
        Path(path_to_download_zip_lotto).mkdir(parents=True, exist_ok=True)
        
        logger.debug(f"copying lottto data from {path_to_download_lotto} to {path_to_download_zip_lotto}")
        sp.call(f"cp {path_to_download_lotto} {path_to_download_zip_lotto}", shell=True)
        
        
        path_to_private_key = Path(
            __file__).parent.parent / f"config/{privatekey}"
        logger.debug(f"path to private key: {path_to_private_key}")
        

        try:
            logger.debug(f"zipping lotto data from {path_to_download_zip_lotto}")
            shutil.make_archive(f"{current_date}", 'zip', path_to_download_zip_lotto, path_to_download_lotto)
            
            logger.info(f'moving zip lotto data from {path_to_download_lotto} to Processed folder on mremote SFTP...')

            child = pexpect.spawn(
                f"sftp -i {path_to_private_key} {username}@{hostname}", timeout=500)

            child.expect(f"Enter passphrase for key '{path_to_private_key}':")
            child.sendline(f"{passphrase}")

            logger.debug(f"----child before-----: {child.before}")

            child.expect("Enter password:")
            child.sendline(f"{password}")

            logger.debug(f"----child before-----: {child.before}")

            child.expect("sftp>")
            child.sendline(f"put {home_path}/*.zip  /Processed/ -resumesupport=off")
            child.expect("sftp>")

            logger.info(f"removing all zip files from {home_path}")
            subprocess.call([f'rm {home_path}/*.zip'], shell=True)


            logger.info(
                'WELL DONE ! Successfully upload all data on remote SFTP.')
            
            # delete all zip files
            logger.debug(f"removing all files and folders from {path_to_download_lotto}")
            subprocess.call([f'rm -rf {path_to_download_lotto}/*'], shell=True)
            
        except pexpect.TIMEOUT as e:
            logger.warning(
                f"SORRY! timeout expired: {e}")
            MpfImportDoclib.send_mail(config)
        except Exception as e:
            logger.error(f"Something went wrong when trying to connect to upload data  on  SFTP...:  {e}")
            

    @classmethod
    def remove_files_dowloaded(cls, config) -> None:
        sftp_config = config["SFTP_CONFIG"]
        unzip_lotto_data = sftp_config["path_download_to_network_share"]
        logger.debug(f"removing all files and folders from {unzip_lotto_data}")
        subprocess.call([f'rm -rf {unzip_lotto_data}/*'], shell=True)
    
    
    def extract_info_from_xml(self, config:dict, current_datetime_lotto:str, lotto_number) -> List[dict]:
        sftp_config = config["SFTP_CONFIG"]
        unzip_lotto_data = sftp_config["path_download_to_network_share"]
        path_for_acces_pdf_files = sftp_config["path_for_access_pdf_files"]
        prefix_path = sftp_config["prefix_path"]  
        xml_file = unzip_lotto_data + "/" + lotto_number + "/" + "indice.xml"
        logger.info(f"start extracting info from {xml_file}...")
        
        tree = ET.parse(xml_file)

        for lotto in tree.iter("LOTTOLAVORAZIONE"):
            logger.debug(f"{lotto.tag}, {lotto.attrib}")
            lotto_id = lotto.attrib['id']
            logger.debug(f"lotto_id: {lotto_id}")

        root = tree.getroot()

        all_data = []
        import_data_dict = {}
        for child in root:
            # set to empty fo each iteration
            import_data_dict = {}
            
            # extract lotto and label for import
            logger.debug(child.tag, child.attrib)
            faldone_id = child.attrib['ID']
            logger.debug(f"faldone_id: {faldone_id}")
            import_data_dict["lotto"] = lotto_id
            import_data_dict["label"] = faldone_id
            
            for refexception in child.find("REFLAVORO"):
                
                # extract reference_description and pages for import
                logger.debug(f"{refexception.tag}, {refexception.text}")
                description = refexception.find("DESCRIZIONE").text
                logger.debug(f"description: {description}")
                import_data_dict["reference_description"] = description
                page = refexception.find("PAGINE").text
                logger.debug(f"page: {page}")
                import_data_dict["pages"] = page
                
                # extract present_in_folder for import
                exist_in_folder = refexception.find("PRESENTE_NEL_FALDONE").text
                logger.debug(f"exist_in_folder: {exist_in_folder}")
                if exist_in_folder == "Y":
                    import_data_dict["present_in_folder"] = True
                else:
                    import_data_dict["present_in_folder"] = False
                # extract reference for import
                number = refexception.find("NUMERO").text
                logger.debug(f"number: {number}")
                import_data_dict["reference"] = number
                
                # extract document_id for import
                document_id = refexception.find("ID").text
                logger.debug(f"document_id: {document_id}")
                import_data_dict["document_id"] = document_id
                
                # extract a single file for each refexception
                filename = refexception.find("FILE").find("NOME").text
                filepath = refexception.find("FILE").find("PERCORSO").text
                logger.debug(f"filepath from xml: {filepath}")
                if filepath is not None:
                    filepath_list = filepath.split("\\")
                    new_file_path = prefix_path + "/" + current_datetime_lotto + "/" + filepath_list[1] + "/" + filepath_list[2] + "/" + filename
                    logger.debug(f"nfilepath: {new_file_path}")
                    import_data_dict["file_relative_url"] = new_file_path
                else:
                    logger.warning(f"filepath from xml is : {filepath} !!! - filename: {filename} was skipped")

                all_data.append(copy.deepcopy(import_data_dict))

        logger.debug(f"all data:\n {all_data}")
        
        return all_data
    
    
    def _encrypt_password(self, password: str, fixed_part: str, ts: float) -> str:
        key_plain = str(fixed_part + str(ts))
        encoded = cryptocode.encrypt(key_plain,password)
        logger.debug(f"encrypt password: {encoded}")
        return encoded

    def send_data_with_api(self, config: dict, all_data: List[dict]) -> None:
        # importing data
        request_config = config["REQUEST_CONFIG"]
        url = request_config["url"]
        password = request_config["password"]
        token_fixed_part = request_config["token_fixed_part"]

        
        for import_data in all_data:
            ct = datetime.now()
            logger.debug(f"current time: {ct}")
            ts = ct.timestamp()
            auth_key = self._encrypt_password(password, token_fixed_part, ts)
            
            hed = {
                'Authorization': 'PWC ' + auth_key, 
                'Content-Type': 'application/json'
            }
            
            import_data = json.dumps(import_data, indent=4)
            response = requests.post(url, data=import_data, headers=hed, verify=False)
            if response.status_code == 201 or response.status_code == 200:
                logger.info(f"{import_data} was successfully imported")
                logger.info(f"POST request success: {response.status_code} - {response.text}")
            else:
                logger.info(f"{import_data} was not imported")
                logger.warning(f"Sorry! POST request failed: {response.status_code} - {response.text}")
            sleep(30)
    
    
    def __random_lotto_number(self, config:dict, chars=string.ascii_uppercase + string.digits, size=10) -> str:
        logger.info("generting random lotto number from lootto file...")
        random_lotto_number = ''.join(random.choice(chars) for _ in range(size))
        return random_lotto_number

    
    
    def copy_lotto_data_for_acces_pdf_files(self, config:dict, lotto_number) -> str:
        logger.info("let's copy lotto data to access pdf files path....")
        sftp_config = config["SFTP_CONFIG"]
        path_for_acces_pdf_files = sftp_config["path_for_access_pdf_files"] 
        unzip_lotto_data = sftp_config["path_download_to_network_share"]
        logger.info(f"copying all files from {unzip_lotto_data} to {path_for_acces_pdf_files}")
        # lotto_number = self.__random_lotto_number(config)
        current_datetime_lotto = str(datetime.today().strftime('%Y_%m_%d')) + '_' + lotto_number
        logger.debug(f"CURRENT DATE + Lotto Number: {current_datetime_lotto}")
        sp.call(f"cd {path_for_acces_pdf_files}", shell=True)
        sp.call(f"mkdir -p {path_for_acces_pdf_files}/{current_datetime_lotto}", shell=True)
        sp.call(f"cd {path_for_acces_pdf_files}/{current_datetime_lotto}", shell=True)
        
        new_dest_path = path_for_acces_pdf_files + f"/{current_datetime_lotto}/"
        sp.call(f"cp -r {unzip_lotto_data}/{lotto_number}/PDF {new_dest_path}", shell=True)
        return current_datetime_lotto
        

        
        
