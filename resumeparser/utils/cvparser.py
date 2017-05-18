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
import datetime

from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

from elasticsearch import Elasticsearch

import sqlite3

conn = sqlite3.connect('respars.sqlite3')
skills_list = [s[1] for s in conn.execute("SELECT * FROM SKILLS")]
ignore_words = [iw[0] for iw in conn.execute("SELECT IgnoreWord FROM ignore_words")]
conn.close()


logging.basicConfig(level=logging.ERROR)

objective = (
    'career goal',
    'objective',
    'career objective',
    'employment objective',
    'professional objective',
    'summary',
    'career summary',
    'professional summary',
    'summary of qualifications',
)

work_and_employment = (
    'employment history',
    'work history',
    'work experience',
    'experience',
    'professional experience',
    'professional background',
    'additional experience',
    'career related experience',
    'related experience',
    'programming experience',
    'freelance',
    'freelance experience',
    'army experience',
    'military experience',
    'military background',
)

education_and_training = (
    'academic background',
    'academic experience',
    'programs',
    'courses',
    'related courses',
    'education',
    'educational background',
    'educational qualifications',
    'educational training',
    'education and training',
    'training',
    'academic training',
    'professional training',
    'course project experience',
    'related course projects',
    'internship experience',
    'internships',
    'apprenticeships',
    'college activities',
    'certifications',
    'special training',
)

skills_header = (
    'credentials',
    'qualifications',
    'areas of experience',
    'areas of expertise',
    'areas of knowledge',
    'skills',
    'career related skills',
    'professional skills',
    'specialized skills',
    'technical skills',
    'computer skills',
    'computer knowledge',
    'software',
    'technologies',
    'technical experience',
    'proficiencies',
    'languages',
    'language competencies and skills',
    'programming languages',
)

misc = (
    'activities and honors',
    'affiliations',
    'professional affiliations',
    'associations',
    'professional associations',
    'memberships',
    'professional memberships',
    'athletic involvement',
    'community involvement',
    'civic activities',
    'extra-Curricular activities',
    'professional activities',
    'volunteer work',
    'volunteer experience',
)

accomplishments = (
    'licenses',
    'presentations',
    'conference presentations',
    'conventions',
    'dissertations',
    'exhibits',
    'papers',
    'publications',
    'professional publications',
    'research',
    'research grants',
    'research projects',
    'current research interests',
    'thesis',
    'theses',
)


def process(file):
    """
    Main function to process resume file to json.
    :param file: Resume file
    :return: resume_data: Parsed resume dictionary
    """
    if file.name.endswith('docx'):
        resume_lines = convert_docx_to_txt(file)
    elif file.name.endswith('pdf'):
        resume_lines = convert_pdf_to_txt(file)
    else:
        return None

    resume_segments = segment(resume_lines)

    resume_data = {
        'contact_info': get_contact_info(resume_segments),
        'education': extract_edu_info(resume_segments, resume_lines[:]),
        'degree': extract_degree_info(resume_segments, resume_lines[:]),
        'work_history': extract_company_info(resume_segments, resume_lines[:]),
        'skills': extract_skills(resume_segments, resume_lines[:]),
    }

    return resume_data


def segment(string_to_search):
    resume_segments = {
        'objective': {},
        'work_and_employment': {},
        'education_and_training': {},
        'skills': {},
        'accomplishments': {},
        'misc': {}
    }

    resume_indices = []

    find_segment_indices(string_to_search, resume_segments, resume_indices)
    slice_segments(string_to_search, resume_segments, resume_indices)

    pretty(resume_segments)
    return resume_segments


def find_segment_indices(string_to_search, resume_segments, resume_indices):
    for i, line in enumerate(string_to_search):

        if line[0].islower():
            continue

        header = line.lower()
        if [o for o in objective if header.startswith(o)]:
            resume_indices.append(i)
            header = [o for o in objective if header.startswith(o)][0]
            resume_segments['objective'][header] = i
        elif [w for w in work_and_employment if header.startswith(w)]:
            resume_indices.append(i)
            header = [w for w in work_and_employment if header.startswith(w)][0]
            resume_segments['work_and_employment'][header] = i
        elif [e for e in education_and_training if header.startswith(e)]:
            resume_indices.append(i)
            header = [e for e in education_and_training if header.startswith(e)][0]
            resume_segments['education_and_training'][header] = i
        elif [s for s in skills_header if header.startswith(s)]:
            resume_indices.append(i)
            header = [s for s in skills_header if header.startswith(s)][0]
            resume_segments['skills'][header] = i
        elif [m for m in misc if header.startswith(m)]:
            resume_indices.append(i)
            header = [m for m in misc if header.startswith(m)][0]
            resume_segments['misc'][header] = i
        elif [a for a in accomplishments if header.startswith(a)]:
            resume_indices.append(i)
            header = [a for a in accomplishments if header.startswith(a)][0]
            resume_segments['accomplishments'][header] = i


def slice_segments(string_to_search, resume_segments, resume_indices):
    resume_segments['contact_info'] = string_to_search[:resume_indices[0]]

    for section, value in resume_segments.items():
        if section == 'contact_info':
            continue

        for sub_section, start_idx in value.items():
            end_idx = len(string_to_search)
            if (resume_indices.index(start_idx) + 1) != len(resume_indices):
                end_idx = resume_indices[resume_indices.index(start_idx) + 1]

            resume_segments[section][sub_section] = string_to_search[start_idx:end_idx]


def get_contact_info(resume_segments):
    """
    Constructs and returns contact_info dictionary.
    :param resume_segments: Dictionary of segmented resume data
    :return: contact_info: Dictionary containing contact info
    """
    contact_info = {
        'person_name': {},
        'contact_method': {}
    }
    # Parse person's name
    contact_info['person_name']['full_name'] = extract_name(resume_segments)
    if contact_info['person_name']['full_name']:
        tokenized_name = contact_info['person_name']['full_name'].split()
        contact_info['person_name']['given_name'] = tokenized_name[0]
        contact_info['person_name']['family_name'] = tokenized_name[-1]
    # Parse contact method
    contact_info['contact_method']['telephone'] = extract_phone_number(resume_segments)
    contact_info['contact_method']['email'] = extract_email(resume_segments)
    contact_info['contact_method']['address'] = {
        'street_address': extract_address(resume_segments),
        'state': extract_state(resume_segments),
        'zipcode': extract_zip(resume_segments)
    }

    return contact_info


def _process_txt(tokens, stop_words):
    return ' '.join([word for word in tokens if word not in stop_words])


def _flatten_dict(list_dict):
    list_values = []
    for key, val in list_dict.items():
        if isinstance(val, list):
            list_values += val

    return list_values


def _get_date_range(string_to_search, start_idx):
    resume_len = len(string_to_search)
    text_to_search = string_to_search[start_idx]
    if (start_idx + 1) < resume_len:
        text_to_search = text_to_search + ' ' + string_to_search[start_idx + 1]
        if (start_idx + 2) < resume_len:
            text_to_search = text_to_search + ' ' + string_to_search[start_idx + 2]

    # list of dates found
    dates = list(datefinder.find_dates(text_to_search))
    # Sanity test for dates
    dates = [date for date in dates
             if datetime.datetime(year=1960, month=1,day=1) < date < datetime.datetime.today()]

    return dates


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

        return resume_lines

    except Exception as e:
        logging.error('Error in pdf file:: ' + str(e))
        return []


def extract_name(resume_segments):
    """
       Find name in the string_to_search
       :param resume_segments: Dictionary containing segmented resume data
       :type resume_segments: Dictionary
       :return: A string containing the name, or None if no name is found.
       :rtype: str
    """
    try:
        string_to_search = resume_segments['contact_info']
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


def extract_phone_number(resume_segments):
    """
        Find first phone number in the string_to_search
        :param resume_segments: Dictionary containing segmented resume data
        :type resume_segments: Dictionary
        :return: A string containing the first phone number, or None if no phone number is found.
        :rtype: str
    """
    try:
        string_to_search = resume_segments['contact_info']
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


def extract_email(resume_segments):
    """
       Find first email address in the string_to_search
       :param resume_segments: Dictionary containing segmented resume data
       :type resume_segments: Dictionary
       :return: A string containing the first email address, or None if no email address is found.
       :rtype: str
       """
    try:
        string_to_search = resume_segments['contact_info']
        email_pattern = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,4}", re.IGNORECASE)
        for line in string_to_search:
            result = re.search(email_pattern, line)
            if result:
                result_groups = result.group()
                return result_groups

    except Exception as e:
        logging.error('Issue parsing email number: ' + str(e))
        return None


def extract_address(resume_segments):
    """
       Find first physical address in the string_to_search
       :param resume_segments: Dictionary containing segmented resume data
       :type resume_segments: Dictionary
       :return: A string containing the first address, or None if no physical address is found.
       :rtype: str
    """
    try:
        string_to_search = resume_segments['contact_info']
        for line in string_to_search:
            result = re.search(street_address, line)
            if result:
                str_addr = result.group().strip(',')
                return str_addr
    except Exception as e:
        logging.error('Issue parsing address:: ' + str(e))
        return None


def extract_state(resume_segments):
    """
       Find first text which matches one of the states in the string_to_search
       :param resume_segments: Dictionary containing segmented resume data
       :type resume_segments: Dictionary
       :return: state code
       :rtype: str
    """
    try:
        string_to_search = resume_segments['contact_info']
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


def extract_zip(resume_segments):
    """
       Find first 5 digits which occour together in the string_to_search
       :param resume_segments: Dictionary containing segmented resume data
       :type resume_segments: Dictionary
       :return: A string containing the zipcode, or None if no zipcode is found.
       :rtype: str
    """
    try:
        string_to_search = resume_segments['contact_info']
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


def extract_edu_info(resume_segments, string_to_search):
    try:
        es = Elasticsearch()
        universities = []
        university_words = ('university', 'institute', 'college')

        edu_info = resume_segments['education_and_training']
        if edu_info:
            string_to_search = _flatten_dict(edu_info)

        for line in string_to_search:

            if not [uw for uw in university_words if uw in line.lower()]:
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


def extract_degree_info(resume_segments, string_to_search):
    try:
        degrees = []

        edu_info = resume_segments['education_and_training']
        if edu_info:
            string_to_search = _flatten_dict(edu_info)

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


def extract_company_info(resume_segments, string_to_search):
    try:
        es = Elasticsearch()
        companies = []
        spl_chars = ['.', ',', '"', "'", '?', '!', ':', ';', '(', ')', '[', ']', '{', '}']
        company_suffixes = ["corporation", "company", "incorporated", "limited", "co", "ltd",
                            "corp", "inc", "llc", "lc", "llp", "psc", "pllc", "plc"]
        stop_words = set()
        stop_words.update(spl_chars)
        stop_words.update(company_suffixes)

        work_info = resume_segments['work_and_employment']
        if work_info:
            string_to_search = _flatten_dict(work_info)

        for i, line in enumerate(string_to_search):

            # Ignore line if line contains more than 10 words
            if len(line.split()) > 10:
                continue

            # remove punctuation and ignore words from line
            line = _process_txt(word_tokenize(line.lower()), ignore_words + spl_chars)

            # Elasticsearch query
            body = {
                "query": {
                    "match": {
                        "name": line
                    }
                }
            }

            # Search elasticsearch companies index
            filter_results = es.search(index='companies', doc_type="company", body=body,
                                       filter_path=['hits.hits._source.name', 'hits.hits._score', 'hits.total'])

            # Go to next line if no results are found
            if not filter_results['hits']['total']:
                continue

            # Convert elasticsearch result to
            company_list = []
            for doc in filter_results['hits']['hits']:
                company_list.append(doc['_source']['name'])

            worked_companies = []
            for c in company_list:
                # Split company name into tokens
                tokenized_c = word_tokenize(c.lower())
                # Company name without punctuations or suffixes
                processed_c = _process_txt(tokenized_c, stop_words)
                company_values = [w['organization'] for w in worked_companies]

                # Check for duplicates
                duplicate_c = [w for w in company_values
                                 if processed_c == _process_txt(
                                    word_tokenize(w.lower()), stop_words)]
                if duplicate_c:
                    continue

                # Check company name in line
                if processed_c in line:
                    # Get the work period
                    work_period = _get_date_range(string_to_search, i)
                    # If no work period dismiss company name
                    if not work_period:
                        continue

                    # Company data dictionary
                    company_data = {
                        'organization': c,
                        'start_date': work_period[0]
                    }

                    # Check for end_date
                    if len(work_period) > 1:
                        company_data['end_date'] = work_period[1]

                    # Add company data to worked companies list
                    worked_companies.append(company_data)

            companies += worked_companies

        return companies

    except Exception as e:
        logging.error('Issue extracting company info:: ' + str(e))
        return []


def extract_skills(resume_segments, string_to_search):
    skills_dict = resume_segments['skills']
    if skills_dict:
        string_to_search = _flatten_dict(skills_dict)

    stop_words = set(stopwords.words('english'))
    stop_words.update(['.', ',', '"', "'", '?', '!', ':', ';', '(', ')', '[', ']', '{', '}'])
    found_skills = []
    for line in string_to_search:
        processed_text = [text.lower() for text in word_tokenize(line) if text not in stop_words]
        found_skills += [s for s in skills_list if s.lower() in processed_text and s not in found_skills]

    skill_count = {}
    for skill in found_skills:
        skill_count[skill] = found_skills.count(skill)

    print("\n===============\n" + str(skill_count) + "\n===============\n")
    return list(set(found_skills))


def pretty(d, indent=0):
   # TODO: For debug purpose. Remove before production
   for key, value in d.items():
      print('\t' * indent + str(key))
      if isinstance(value, dict):
         pretty(value, indent+1)
      else:
         print('\t' * (indent+1) + str(value))


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