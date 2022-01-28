# import python standard libraries
import os
import argparse
import logging.config
from pathlib import Path

# internal imports
from library.mpf_import_doc_lib import MpfImportDoclib


logs_directory = Path(Path(__file__).parent / "logs").mkdir(parents=True, exist_ok=True)

# logging
logging.config.fileConfig(os.path.join(os.getcwd(), "config/logging.ini"), disable_existing_loggers=False)

# create a logger
logger = logging.getLogger('mpf_import_doc')

def mpf_import_doc():
    logger.info("start mpf_import_doc...")
    config = MpfImportDoclib.load_configuration()
    MpfImportDoclib.sftp_connect_download(config)
    if MpfImportDoclib.check_downloaded_files(config) == True:
        mpfImportDocLib = MpfImportDoclib(config)
        current_date = MpfImportDoclib.move_data_to_backup(config)
        MpfImportDoclib.move_data_to_processed(config, current_date)
        MpfImportDoclib.remove_files_dowloaded(config)
    else:
        logger.info("No data was downloaded! There is no new data on remote SFTP")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('--old', '-o', type=str,
                        help='execute old import java program', required=True)
    
    args = parser.parse_args()
    logger.debug(f"argument: {args.old}")
    try:
        if args.old =="no":   
            mpf_import_doc()
        elif args.old =="yes":
            config = MpfImportDoclib.load_configuration()
            MpfImportDoclib.sftp_connect_download(config)
            if MpfImportDoclib.check_downloaded_files(config) == True:
                MpfImportDoclib.move_data_to_backup(config)
                MpfImportDoclib.move_data_to_processed(config)
            else:
                logger.info("No data was downloaded! There is no new data on remote SFTP")
            logger.info("Bye! old JAVA program will be executed...")
        else:
            logger.error(f"{args.old} is not valid: valid values are <yes> or <no>")
    except Exception as e:
        logger.error(f"Something went wrong while executing mpf import doc: {e}")
