import logging
import re

import docx2txt

from pdfminer.converter import TextConverter
from pdfminer.layout import LAParams
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.pdfpage import PDFPage
from io import StringIO

from commonregex import street_address

import datefinder

from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

from elasticsearch import Elasticsearch

import sqlite3

conn = sqlite3.connect('respars.sqlite3')
skills = [s[1] for s in conn.execute("SELECT * FROM SKILLS")]
ignore_words = [iw[0] for iw in conn.execute("SELECT IgnoreWord FROM ignore_words")]
conn.close()

import csv
import editdistance

logging.basicConfig(level=logging.ERROR)

work_headers = (
    'work experience',
    'professional experience',
    'professional summary',
    'experience',
    'projects',
    'project details',
    'career summary',
)

education_headers = (
    'education',
    'educational',
    'qualifications',
)

header_indices = {
    'education': 0,
    'work': 0
}


def _ismatch(matchlist, search_string):
    search_string = search_string.lower()
    for item in matchlist:
        if item in search_string:
            return True
    return False


def _get_header_idx(string_to_search, header_list):
    for header in header_list:
        for idx, line in enumerate(string_to_search):
            cond1 = len(line.split()) < 5  # Line contains less than 5 words
            cond2 = header in line.lower()  # header is present in the line
            if cond1 and cond2:
                return idx  # Return the index of the line
    return 0


def _set_header_indices(resume_lines):
    header_indices['education'] = _get_header_idx(resume_lines, education_headers)
    header_indices['work'] = _get_header_idx(resume_lines, work_headers)


def _get_segment(string_to_search, start_idx, end_idx):
    if start_idx < end_idx:
        return string_to_search[start_idx: end_idx]
    else:
        return string_to_search[start_idx:]


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
        text = docx2txt.process(docx_file)  # Extract text from docx file
        clean_text = text.replace("\r", "\n").replace("\t", " ")  # Normalize text blob
        resume_lines = clean_text.splitlines()  # Split text blob into individual lines
        resume_lines = [line.strip() for line in resume_lines if line.strip()]  # Remove empty strings and whitespaces

        # Set header indices
        _set_header_indices(resume_lines)

        return resume_lines
    except Exception as e:
        logging.error('Error in docx file:: ' + str(e))
        return []


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
        full_string = full_string.replace("\t", " ")

        # Remove awkward LaTeX bullet characters
        full_string = re.sub(r"\(cid:\d{0,2}\)", " ", full_string)

        # Split text blob into individual lines
        resume_lines = full_string.splitlines(True)

        # Remove empty strings and whitespaces
        resume_lines = [re.sub('\s+', ' ', line.strip()) for line in resume_lines if line.strip()]

        # Set header indices
        _set_header_indices(resume_lines)

        return resume_lines

    except Exception as e:
        logging.error('Error in pdf file:: ' + str(e))
        return []


def extract_name(string_to_search):
    """
       Find name in the string_to_search
       :param string_to_search: A string to check for a name
       :type string_to_search: str
       :return: A string containing the name, or None if no name is found.
       :rtype: str
    """
    try:
        string_to_search = _get_segment(string_to_search, 0, min(header_indices['education'], header_indices['work']))
        name_pattern = re.compile(r"^([A-Za-z\u00E9-\u00F8\.-][\s]*)+$")
        name = ''
        for line in string_to_search:
            if name_pattern.match(line):
                name = line
                break

        return name

    except Exception as e:
        logging.error('Issue parsing name:: ' + str(e))
        return None


def extract_phone_number(string_to_search):
    """
        Find first phone number in the string_to_search
        :param string_to_search: A string to check for a phone number in
        :type string_to_search: str
        :return: A string containing the first phone number, or None if no phone number is found.
        :rtype: str
    """
    try:
        string_to_search = _get_segment(string_to_search, 0, min(header_indices['education'], header_indices['work']))
        regular_expression = re.compile(r"\(?"  # open parenthesis
                                        r"(\d{3})?"  # area code
                                        r"\)?"  # close parenthesis
                                        r"[\s\.-]{0,2}?"  # area code, phone separator
                                        r"(\d{3})"  # 3 digit exchange
                                        r"[\s\.-]{0,2}"  # separator bbetween 3 digit exchange, 4 digit local
                                        r"(\d{4})",  # 4 digit local
                                        re.IGNORECASE)
        for line in string_to_search:
            result = re.search(regular_expression, line)
            if result:
                result_groups = result.groups()
                phone_no = "-".join(result_groups)
                return phone_no

        return None
    except Exception as e:
        logging.error('Issue parsing phone number:: ' + str(e))
        return None


def extract_email(string_to_search):
    """
       Find first email address in the string_to_search
       :param string_to_search: A string to check for an email address in
       :type string_to_search: str
       :return: A string containing the first email address, or None if no email address is found.
       :rtype: str
       """
    try:
        string_to_search = _get_segment(string_to_search, 0, min(header_indices['education'], header_indices['work']))
        email_pattern = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,4}", re.IGNORECASE)
        for line in string_to_search:
            result = re.search(email_pattern, line)
            if result:
                result_groups = result.group()
                return result_groups

    except Exception as e:
        logging.error('Issue parsing email number: ' + str(e))
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
        string_to_search = _get_segment(string_to_search, 0, min(header_indices['education'], header_indices['work']))
        for line in string_to_search:
            result = re.search(street_address, line)
            if result:
                str_addr = result.group().strip(',')
                return str_addr
    except Exception as e:
        logging.error('Issue parsing address:: ' + str(e))
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
        string_to_search = _get_segment(string_to_search, 0, min(header_indices['education'], header_indices['work']))
        states = ['AK', 'AL', 'AR', 'AZ', 'CA', 'CO', 'CT', 'DC', 'DE', 'FL', 'GA', 'HI', 'IA', 'ID',
                  'IL', 'IN', 'KS', 'KY', 'LA', 'MA', 'MD', 'ME', 'MI', 'MN', 'MO', 'MS', 'MT', 'NC', 'ND', 'NE',
                  'NH', 'NJ', 'NM', 'NV', 'NY', 'OH', 'OK', 'OR', 'PA', 'PR', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT',
                  'VA', 'VT', 'WA', 'WI', 'WV', 'WY']
        state_pattern = re.compile(r'\b(' + '|'.join(states) + r')\b')
        for line in string_to_search:
            result = state_pattern.search(line)
            if result:
               return result.group()

        return None
    except Exception as e:
        logging.error('Issue parsing state:: ' + str(e))
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
        string_to_search = _get_segment(string_to_search, 0, min(header_indices['education'], header_indices['work']))
        for line in string_to_search:
            result = re.search("[\s-][0-9]{5}[\s,.]|[\s-][0-9]{5}$", line)
            if result:
                result_group = result.group()
                zip_code = re.search(r"[0-9]{5}", result_group).group()
                return zip_code
        return None

    except Exception as e:
        logging.error('Issue parsing zip:: ' + str(e))
        return None


def extract_edu_info(string_to_search):
    try:
        es = Elasticsearch()
        universities = []
        university_words = ('university', 'institute', 'college')

        string_to_search = _get_segment(string_to_search, header_indices['education'],
                                        header_indices['work'])

        for line in string_to_search:

            if not _ismatch(university_words, line):
                continue

            body = {
                "query": {
                    "match": {
                        "name": line
                    }
                }
            }
            filter_results = es.search(index='universities', doc_type="university", body=body,
                                       filter_path=['hits.hits._source.name', 'hits.hits._score', 'hits.total'])

            if not filter_results['hits']['total']:
                continue

            university_list = []
            for doc in filter_results['hits']['hits']:
                university_list.append(doc['_source']['name'])

            univ_found = [ut for ut in university_list if re.search(ut, line)]

            if not univ_found:
                for u in university_list:
                    u_temp = u.replace('The ', '')
                    if 'at' in u_temp:
                        u_split = u_temp.split(' at ')
                    else:
                        u_split = u_temp.split(',')

                    u_name = u_split[0]
                    if len(u_split) > 1:
                        u_loc = u_split[1]
                    else:
                        u_loc = ' '

                    if u_name.lower() in line.lower() and u_loc.lower() in line.lower():
                        univ_found.append(u)
                    elif u_name.lower() in line.lower():
                        univ_found.append(u_name)

            universities += univ_found

        return list(set(universities))

    except Exception as e:
        logging.error('Issue extracting education info:: ' + str(e))
        return []


def extract_degree_info(string_to_search):
    try:
        degrees = []
        string_to_search = _get_segment(string_to_search, header_indices['education'], header_indices['work'])

        for line in string_to_search:
            if len(line.split()) > 15:
                continue

            if 'Bachelor' in line or 'B.' in line or 'BS' in line:
                degrees.append('BS')
            if 'Master' in line or 'M.' in line or 'MS' in line:
                degrees.append('MS')
            if 'Doctorate' in line or 'Doctor of Philosophy' in line or 'Ph.d.' in line :
                degrees.append('Ph.D.')
            if 'MBA' in line:
                degrees.append('MBA')

        return list(set(degrees))

    except Exception as e:
        logging.error('Issue extracting degree info:: ' + str(e))
        return []


def _process_txt(tokens, stop_words):
    return ' '.join([word for word in tokens if word not in stop_words])


def _get_date_range(string_to_search, start_idx):
    resume_len = len(string_to_search)
    text_to_search = string_to_search[start_idx]
    if (start_idx + 1) < resume_len:
        text_to_search = text_to_search + ' ' + string_to_search[start_idx + 1]
        if (start_idx + 2) < resume_len:
            text_to_search = text_to_search + ' ' + string_to_search[start_idx + 2]

    dates = list(datefinder.find_dates(text_to_search))
    return dates


def extract_company_info(string_to_search):
    try:
        es = Elasticsearch()
        companies = []

        es = Elasticsearch()
        lc_skills = [s.lower() for s in skills]
        spl_chars = ['.', ',', '"', "'", '?', '!', ':', ';', '(', ')', '[', ']', '{', '}']
        company_suffixes = ["corporation", "company", "incorporated", "limited", "co", "ltd"
                            "corp", "inc", "llc", "lc", "llp", "psc", "pllc", "plc"]
        stop_words = set()
        stop_words.update(spl_chars)
        stop_words.update(company_suffixes)

        string_to_search = _get_segment(string_to_search, header_indices['work'], header_indices['education'])

        for i, line in enumerate(string_to_search):

            if len(line.split()) > 10:
                continue

            line = _process_txt(word_tokenize(line.lower()), ignore_words + spl_chars)

            body = {
                "query": {
                    "match": {
                        "name": line
                    }
                }
            }
            filter_results = es.search(index='companies', doc_type="company", body=body,
                                       filter_path=['hits.hits._source.name', 'hits.hits._score', 'hits.total'])

            if not filter_results['hits']['total']:
                continue

            company_list = []
            for doc in filter_results['hits']['hits']:
                company_list.append(doc['_source']['name'])

            worked_companies = []
            for c in company_list:
                # Split company name into tokens
                tokenized_c = word_tokenize(c.lower())
                # Company name without punctuations or suffixes
                processed_c = _process_txt(tokenized_c, stop_words)
                company_values = [w['name'] for w in worked_companies]
                duplicate_c = [w for w in company_values
                                 if processed_c == _process_txt(word_tokenize(w.lower()), stop_words)]
                if duplicate_c:
                    continue

                if processed_c in line:
                    work_period = _get_date_range(string_to_search, i)
                    if not work_period:
                        continue

                    company_data = {
                        'name': c,
                        'start_date': work_period[0]
                    }

                    if len(work_period) > 1:
                        company_data['end_date'] = work_period[1]

                    worked_companies.append(company_data)

                # if processed_c in line:
                #     # TODO: Rewrite skills detection logic
                #     # Check if company name matches any in skill list
                #     cond1 = [t for t in tokenized_c if t in lc_skills]
                #     if not cond1:
                #         worked_companies.append(c)
                #         continue
                #
                #     # Company name contains words which match a skill
                #     # RegEx to find spl chars
                #     spl_chars_regex = re.compile('|'.join(map(re.escape, spl_chars)))
                #     # Company name without punctuation
                #     processed_c2 = spl_chars_regex.sub("", c.lower())
                #     # Check if company name with suffix in line
                #     cond2 = processed_c2 in line
                #     if cond1 and cond2:
                #         worked_companies.append(c)

            companies += worked_companies

        return companies

    except Exception as e:
        logging.error('Issue extracting company info:: ' + str(e))
        return []


def extract_skills(string_to_search):

    stop_words = set(stopwords.words('english'))
    stop_words.update(['.', ',', '"', "'", '?', '!', ':', ';', '(', ')', '[', ']', '{', '}'])
    found_skills = []
    for line in string_to_search:
        processed_text = [text.lower() for text in word_tokenize(line) if text not in stop_words]
        found_skills += [s for s in skills if s.lower() in processed_text and s not in found_skills]

    skill_count = {}
    for skill in found_skills:
        skill_count[skill] = found_skills.count(skill)

    print("\n===============\n" + str(skill_count) + "\n===============\n")
    return list(set(found_skills))


def process(file):
    if file.name.endswith('docx'):
        resume_lines = convert_docx_to_txt(file)
    elif file.name.endswith('pdf'):
        resume_lines = convert_pdf_to_txt(file)
    else:
        return None

    resume_data = {
        'name': extract_name(resume_lines),
        'email': extract_email(resume_lines),
        'phone_number': extract_phone_number(resume_lines),
        'street_address': extract_address(resume_lines),
        'state': extract_state(resume_lines),
        'zipcode': extract_zip(resume_lines),
        'education': extract_edu_info(resume_lines),
        'degree': extract_degree_info(resume_lines),
        'work_history': extract_company_info(resume_lines),
        'skills': extract_skills(resume_lines),
    }

    return resume_data


# def print_distance(name, email):
#     orig_name = name
#     orig_email = email
#     name = name.replace(' ', '').lower()
#     if email:
#         email = email.split('@')[0]
#         email = re.sub(r'[\.-_0-9]+', '', email)
#         score = str(editdistance.eval(name, email))
#
#         with open('ne_distance.csv', 'a') as csvfile:
#             fieldnames = ['name', 'email', 'score']
#             writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
#             writer.writerow({'name': orig_name, 'email': orig_email, 'score' : score})