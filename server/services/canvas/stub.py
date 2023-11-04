class DictWrapperObject:
    def __init__(self, dic):
        self.__dict__.update(dic)


def _dict_to_object(dic):
    return DictWrapperObject(dic)


DEV_USER_DB = {
    '123456': {
        'id': 123456,
        'name': 'Yu Long',
        'global_id': '10000000000000',
        'effective_locale': 'en'
    },
    '234567': {
        'id': 234567,
        'name': 'Jimmy Xu',
        'global_id': '10000000000001',
        'effective_locale': 'en'
    }
}


def get_dev_user(user_id):
    return _dict_to_object(DEV_USER_DB[str(user_id)])


DEV_COURSE_DB = {
    '1234567': {
        'id': 1234567,
        'name': 'Introduction to Software Engineering (Fall 2023)',
        'sis_course_id': 'CRS:COMPSCI-169A-2023-D',
        'course_code': 'COMPSCI 169A-LEC-001',
    },
    '2345678': {
        'id': 2345678,
        'name': 'Introduction to the Internet: Architecture and Protocols (Fall 2022)',
        'sis_course_id': '',
        'course_code': 'COMPSCI 168',
    }
}


def get_dev_course(course_id):
    return _dict_to_object(DEV_COURSE_DB[str(course_id)])


DEV_ENROLLMENT_DB = {
    '123456': {
        '1234567':
            {
                'enrollments': [
                    {'type': 'ta', 'role': 'TaEnrollment', 'enrollment_state': 'active'}
                ]
            },
        '2345678':
            {
                'enrollments': [
                    {'type': 'student', 'role': 'StudentEnrollment', 'enrollment_state': 'active'}
                ]
            }
    },
    '234567': {
        '1234567':
            {
                'enrollments': [
                    {'type': 'student', 'role': 'StudentEnrollment', 'enrollment_state': 'active'}
                ]
            },
        '2345678':
            {
                'enrollments': [
                    {'type': 'ta', 'role': 'TaEnrollment', 'enrollment_state': 'active'}
                ]
            }
    },
}


def get_dev_user_courses(user_id):
    dic = DEV_ENROLLMENT_DB[str(user_id)]
    return [_dict_to_object(DEV_COURSE_DB[str(course_id)] | dic[str(course_id)])
            for course_id in dic.keys()]


def get_dev_user_oauth_resp(user_id):
    return {
        'access_token': 'dev_access_token',
        'token_type': 'Bearer',
        'user': DEV_USER_DB[str(user_id)],
        'canvas_region': 'us-east-1',
        'refresh_token': 'dev_refresh_token',
        'expires_in': 3600
    }
