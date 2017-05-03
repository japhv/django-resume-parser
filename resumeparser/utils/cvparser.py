import logging
import re

import docx2txt

from pdfminer.converter import TextConverter
from pdfminer.layout import LAParams
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.pdfpage import PDFPage
from io import StringIO

from commonregex import street_address

from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

from elasticsearch import Elasticsearch

import sqlite3

logging.basicConfig(level=logging.ERROR)

conn = sqlite3.connect('respars.sqlite3')
university = [u[0] for u in conn.execute("SELECT * from UNIVERSITIES")]
company = [c[0] for c in conn.execute("SELECT * from COMPANIES")]
degree = [{'abbr': d[0], 'title': d[1]} for d in conn.execute("SELECT * from DEGREE")]
skills = [s[1].lower() for s in conn.execute("SELECT * FROM SKILLS")]
conn.close()


def convert_docx_to_txt(docx_file):
    """
        A utility function to convert a Microsoft docx files to raw text.

        This code is largely borrowed from existing solutions, and does not match the style of the rest of this repo.
        :param docx_file: docx file with gets uploaded by the user
        :type docx_file: InMemoryUploadedFile
        :return: The text contents of the docx file
        :rtype: str
        """
    try:
        text = docx2txt.process(docx_file)
        clean_text = text.replace("\r", "\n").replace("\n", " ").replace("\t", " ")
        return clean_text
    except Exception as e:
        logging.error('Error in file: ' + str(e))
        return ''


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
    """
       Find first text which matches one of the states in the string_to_search
       :param string_to_search: A string to check for a state code
       :type string_to_search: str
       :return: state code
       :rtype: str
    """
    try:
        states = ['AK', 'AL', 'AR', 'AZ', 'CA', 'CO', 'CT', 'DC', 'DE', 'FL', 'GA', 'HI', 'IA', 'ID',
                  'IL', 'IN', 'KS', 'KY', 'LA', 'MA', 'MD', 'ME', 'MI', 'MN', 'MO', 'MS', 'MT', 'NC', 'ND', 'NE',
                  'NH', 'NJ', 'NM', 'NV', 'NY', 'OH', 'OK', 'OR', 'PA', 'PR', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT',
                  'VA', 'VT', 'WA', 'WI', 'WV', 'WY']
        result = re.compile(r'\b(' + '|'.join(states) + r')\b')
        result = result.findall(string_to_search)[0]
        if result:
            return result
        return ""
    except Exception as e:
        logging.error('Issue parsing address:: ' + str(e))
        return None


def extract_zip(string_to_search):
    """
       Find first 5 digits which occour together in the string_to_search
       :param string_to_search: A string to check for a zipcode
       :type string_to_search: str
       :return: A string containing the zipcode, or None if no zipcode is found.
       :rtype: str
    """
    try:
        zip_code = re.findall("[\s-][0-9]{5}[\s,]", string_to_search)
        if zip_code:
            return re.findall("[0-9]{5}", zip_code[0])[0]
        return None

    except Exception as e:
        logging.error('Issue parsing zip:: ' + str(e))
        return None


def extract_name(string_to_search):
    """
       Find name in the string_to_search
       :param string_to_search: A string to check for a name
       :type string_to_search: str
       :return: A string containing the name, or None if no name is found.
       :rtype: str
    """
    try:
        nameRegex = "[A-Za-z\u00E9-\u00F8]+\s+[A-Za-z\u00E9-\u00F8]+"
        nameSearch = re.findall(nameRegex, string_to_search)
        return nameSearch[0]

    except Exception as e:
        logging.error('Issue parsing name:: ' + str(e))
        return None


def extract_edu_info(string_to_search):
    try:
        start_idx = string_to_search.lower().find('education')
        if start_idx != -1:
            start_idx += 10
            end_idx = start_idx + 450
            string_to_search = string_to_search[start_idx: end_idx]
            string_to_search = ' '.join(string_to_search.split())

        es = Elasticsearch()
        body = {
            "query": {
                "match": {
                    "name": string_to_search
                }
            }
        }
        filter_results = es.search(index='universities', doc_type="university", body=body,
                                   filter_path=['hits.hits._source.name', 'hits.hits._score', 'hits.total'])
        university_list = []
        for doc in filter_results['hits']['hits']:
            university_list.append(doc['_source']['name'])

        universities = [ut for ut in university_list if re.search(ut, string_to_search)]

        if not universities:
            for u in university_list:
                u_temp = u.lower().replace('the', '')
                if 'at' in u_temp:
                    u_split = u_temp.split('at')
                else:
                    u_split = u_temp.split(',')

                u_name = u_split[0]
                if len(u_split) > 1:
                    u_loc = u_split[1]
                else:
                    u_loc = ' '

                if u_name in string_to_search.lower() and u_loc in string_to_search.lower():
                    universities.append(u)


        return universities

    except Exception as e:
        logging.error('Issue extracting education info:: ' + str(e))
        return []


def extract_degree_info(string_to_search):
    try:
        start_idx = string_to_search.lower().find('education')
        if start_idx != -1:
            start_idx += 10
            end_idx = start_idx + 500
            string_to_search = string_to_search[start_idx: end_idx]

        # degrees = [d['abbr'] for d in degree if re.search(d['abbr'], string_to_search)
        #                  or re.search(d['title'], string_to_search)]
        degrees = []
        lc_string = string_to_search.lower()
        if 'bachelor' in lc_string or ' b.' in lc_string or ' bs ' in lc_string :
            degrees.append('BS')
        if 'master' in lc_string or ' m.' in lc_string or ' ms ' in lc_string:
            degrees.append('MS')
        if 'doctorate' in lc_string or 'doctor of philosophy' in lc_string or 'ph.d.' in lc_string :
            degrees.append('Ph.D.')

        return degrees

    except Exception as e:
        logging.error('Issue extracting degree info:: ' + str(e))
        return None


def extract_company_info(string_to_search):
    try:
        es = Elasticsearch()
        company_list = []
        stop_words = set(stopwords.words('english'))
        stop_words.update(['.', ',', '"', "'", '?', '!', ':', ';', '(', ')', '[', ']', '{', '}'])
        stop_words.update(["corporation", "company", "incorporated", "limited", "co", "ltd"
                           "corp", "inc", "llc", "lc", "llp", "psc", "pllc", "plc", "sales", "Sales"])
        sub_headers = (
            'work experience',
            'professional experience',
            'professional summary',
            'experience',
            'projects',
            'project details',
            'career summary'
        )
        processed_text = ([text for text in word_tokenize(string_to_search) if text not in stop_words
                           and text[0].isupper()])

        string_to_search = ' '.join(processed_text).lower()

        for header in sub_headers:
            start_idx = string_to_search.find(header)
            if start_idx != -1:
                start_idx += len(header)
                string_to_search = string_to_search[start_idx:]
                break

        we_keywords = string_to_search.split(' ')
        we_chunks = [we_keywords[x:x + 10] for x in range(0, len(we_keywords), 10)]

        for chuck in we_chunks:
            body = {
                "query": {
                    "match": {
                        "name": ' '.join(chuck)
                    }
                }
            }
            filter_results = es.search(index='companies', doc_type="company", body=body,
                                       filter_path=['hits.hits._source.name', 'hits.hits._score', 'hits.total'])

            for doc in filter_results['hits']['hits']:
                company_list.append(doc['_source']['name'])

        worked_companies = []
        for c in company_list:
            processed_c = ' '.join([word for word in word_tokenize(c.lower()) if word not in stop_words])
            if processed_c in string_to_search:
                worked_companies.append(c)

        return worked_companies

    except Exception as e:
        logging.error('Issue extracting company info:: ' + str(e))
        return []


def extract_skills(string_to_search):

    stop_words = set(stopwords.words('english'))
    stop_words.update(['.', ',', '"', "'", '?', '!', ':', ';', '(', ')', '[', ']', '{', '}'])
    processed_text = [text.lower() for text in word_tokenize(string_to_search) if text not in stop_words]
    found_skills = [s for s in skills if s in processed_text]
    return found_skills