import logging
import re

from pdfminer.converter import TextConverter
from pdfminer.layout import LAParams
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.pdfpage import PDFPage
from io import StringIO

from commonregex import street_address

from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

import sqlite3

logging.basicConfig(level=logging.ERROR)

conn = sqlite3.connect('respars.sqlite3')
university = [u[0] for u in conn.execute("SELECT * from UNIVERSITIES")]
company = [c[0] for c in conn.execute("SELECT * from COMPANIES")]
degree = [{'abbr': d[0], 'title': d[1]} for d in conn.execute("SELECT * from DEGREE")]
skills = [s[1].lower() for s in conn.execute("SELECT * FROM SKILLS")]
conn.close()


def convert_pdf_to_txt(pdf_file):
    """
    A utility function to convert a machine-readable PDF to raw text.

    This code is largely borrowed from existing solutions, and does not match the style of the rest of this repo.
    :param input_pdf_path: Path to the .pdf file which should be converted
    :type input_pdf_path: str
    :return: The text contents of the pdf
    :rtype: str
    """
    try:
        # PDFMiner boilerplate
        rsrcmgr = PDFResourceManager()
        retstr = StringIO()
        codec = 'utf-8'
        laparams = LAParams()
        device = TextConverter(rsrcmgr, retstr, codec=codec, laparams=laparams)
        interpreter = PDFPageInterpreter(rsrcmgr, device)

        # Iterate through pages
        for page in PDFPage.get_pages(pdf_file, set(), maxpages=0, password='',
                                      caching=True, check_extractable=True):
            interpreter.process_page(page)
        device.close()

        # Get full string from PDF
        full_string = retstr.getvalue()
        retstr.close()

        # Normalize a bit, removing line breaks
        full_string = full_string.replace("\r", "\n")
        full_string = full_string.replace("\n", " ")

        # Remove awkward LaTeX bullet characters
        full_string = re.sub(r"\(cid:\d{0,2}\)", " ", full_string)
        return full_string

    except Exception as e:
        logging.error('Error in file: ' + str(e))
        return ''


def extract_phone_number(string_to_search):
    """
    Find first phone number in the string_to_search
    :param string_to_search: A string to check for a phone number in
    :type string_to_search: str
    :return: A string containing the first phone number, or None if no phone number is found.
    :rtype: str
    """
    try:
        regular_expression = re.compile(r"\(?"  # open parenthesis
                                        r"(\d{3})?"  # area code
                                        r"\)?"  # close parenthesis
                                        r"[\s\.-]{0,2}?"  # area code, phone separator
                                        r"(\d{3})"  # 3 digit exchange
                                        r"[\s\.-]{0,2}"  # separator bbetween 3 digit exchange, 4 digit local
                                        r"(\d{4})",  # 4 digit local
                                        re.IGNORECASE)
        result = re.search(regular_expression, string_to_search)
        if result:
            result = result.groups()
            result = "-".join(result)
        return result
    except Exception as e:
        logging.error('Issue parsing phone number: ' + string_to_search + str(e))
        return None


def exract_email(string_to_search):
    """
       Find first email address in the string_to_search
       :param string_to_search: A string to check for an email address in
       :type string_to_search: str
       :return: A string containing the first email address, or None if no email address is found.
       :rtype: str
       """
    try:
        regular_expression = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,4}", re.IGNORECASE)
        result = re.search(regular_expression, string_to_search)
        if result:
            result = result.group()
        return result
    except Exception as e:
        logging.error('Issue parsing email number: '  + str(e))
        return None


def extract_address(string_to_search):
    """
       Find first physical address in the string_to_search
       :param string_to_search: A string to check for a physical address in
       :type string_to_search: str
       :return: A string containing the first address, or None if no physical address is found.
       :rtype: str
       """
    try:
        result = re.search(street_address, string_to_search)
        if result:
            result = result.group().strip(',')

        return result
    except Exception as e:
        logging.error('Issue parsing address: ' + string_to_search + str(e))
        return None


def extract_state(string_to_search):
    try:
        states = ['AK', 'AL', 'AR', 'AZ', 'CA', 'CO', 'CT', 'DC', 'DE', 'FL', 'GA', 'HI', 'IA', 'ID',
                  'IL', 'IN', 'KS', 'KY', 'LA', 'MA', 'MD', 'ME', 'MI', 'MN', 'MO', 'MS', 'MT', 'NC', 'ND', 'NE',
                  'NH', 'NJ', 'NM', 'NV', 'NY', 'OH', 'OK', 'OR', 'PA', 'PR', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT',
                  'VA', 'VT', 'WA', 'WI', 'WV', 'WY']
        result = re.compile(r'\b(' + '|'.join(states) + r')\b', re.IGNORECASE)
        result = result.findall(string_to_search)[0]
        if result:
            return result
        return ""
    except Exception as e:
        logging.error('Issue parsing address: ' + str(e))
        return None


def extract_zip(string_to_search):
    try:
        zip_code = re.findall("[\s-][0-9]{5}[\s,]", string_to_search)
        if zip_code[0]:
            return re.findall("[0-9]{5}", zip_code[0])[0]
        return None

    except Exception as e:
        logging.error('Issue parsing zip: ' + str(e))
        return None


def extract_name(string_to_search):
    try:
        nameRegex = "[A-Za-z]+\s+[A-Za-z]+"
        nameSearch = re.findall(nameRegex, string_to_search)
        return nameSearch[0]

    except Exception as e:
        logging.error('Issue parsing name: ' + str(e))
        return None


def extract_edu_info(string_to_search):
    try:
        start_idx = string_to_search.lower().find('education')
        if start_idx != -1:
            start_idx += 10
            end_idx = start_idx + 500
            string_to_search = string_to_search[start_idx: end_idx]

        universities = [ut for ut in university if re.search(ut, string_to_search)]
        return universities

    except Exception as e:
        logging.error('Issue extracting education info:: ' + str(e))
        return None


def extract_degree_info(string_to_search):
    try:
        start_idx = string_to_search.lower().find('education')
        if start_idx != -1:
            start_idx += 10
            end_idx = start_idx + 500
            string_to_search = string_to_search[start_idx: end_idx]

        degrees = [d['abbr'] for d in degree if re.search(d['abbr'], string_to_search)
                         or re.search(d['title'], string_to_search)]
        return degrees

    except Exception as e:
        logging.error('Issue extracting degree info:: ' + str(e))
        return None


def extract_company_info(string_to_search):
    try:
        for c in company:
            if re.search(c, string_to_search):
                return c

    except Exception as e:
        logging.error('Issue extracting company info:: ' + str(e))
        return None


def extract_skills(string_to_search):

    stop_words = set(stopwords.words('english'))
    stop_words.update(['.', ',', '"', "'", '?', '!', ':', ';', '(', ')', '[', ']', '{', '}'])

    processed_text = [text.lower() for text in word_tokenize(string_to_search) if text not in stop_words]

    found_skills = [s for s in skills if s in processed_text]
    return found_skills