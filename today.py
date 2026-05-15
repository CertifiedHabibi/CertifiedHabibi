import datetime
import base64
import os
import time
import hashlib
import requests
from dateutil import relativedelta
from xml.sax.saxutils import escape as xml_escape

HEADERS   = {'authorization': 'token ' + os.environ['ACCESS_TOKEN']}
USER_NAME = os.environ['USER_NAME']
QUERY_COUNT = {
    'user_getter': 0, 'follower_getter': 0, 'graph_repos_stars': 0,
    'recursive_loc': 0, 'graph_commits': 0, 'loc_query': 0,
}

BIRTHDAY      = datetime.datetime(2005, 10, 26)
PROFILE_IMAGE = 'assets/Me.png'

OS_INFO    = 'Windows 11, Android 14'
HOST_INFO  = 'MIT World Peace University, Pune'
KERNEL_INFO= 'Cloud Computing Student'
IDE_INFO   = 'WebStorm, PyCharm, Rider, VSCode, VS'
LANG_PROG  = 'Python, JavaScript, C++, C#, Lua'
LANG_COMP  = 'HTML, CSS, JSON, LaTeX, YAML'
LANG_REAL  = 'English, Hindi, Gujarati'
HOBBY_SW   = 'Game Modding, Pixel Art'
HOBBY_HW   = 'Playing the Violin, Playing Squash or Table Tennis'
EMAIL      = 'fxswift2610@gmail.com'
LINKEDIN   = 'CertifiedHabibi'
DISCORD    = 'certified._.habibi'

def daily_readme(birthday):
    diff = relativedelta.relativedelta(datetime.datetime.today(), birthday)
    return '{} {}, {} {}, {} {}{}'.format(
        diff.years,  'year'  + ('s' if diff.years  != 1 else ''),
        diff.months, 'month' + ('s' if diff.months != 1 else ''),
        diff.days,   'day'   + ('s' if diff.days   != 1 else ''),
        ' 🎂' if (diff.months == 0 and diff.days == 0) else '',
    )


def simple_request(func_name, query, variables):
    req = requests.post(
        'https://api.github.com/graphql',
        json={'query': query, 'variables': variables},
        headers=HEADERS,
    )
    if req.status_code == 200:
        return req
    raise Exception(func_name, 'failed with', req.status_code, req.text, QUERY_COUNT)


def graph_repos_stars(count_type, owner_affiliation, cursor=None):
    query_count('graph_repos_stars')
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 100, after: $cursor, ownerAffiliations: $owner_affiliation) {
                totalCount
                edges {
                    node {
                        ... on Repository {
                            nameWithOwner
                            stargazers { totalCount }
                        }
                    }
                }
                pageInfo { endCursor hasNextPage }
            }
        }
    }'''
    variables = {'owner_affiliation': owner_affiliation, 'login': USER_NAME, 'cursor': cursor}
    req = simple_request(graph_repos_stars.__name__, query, variables)
    if count_type == 'repos':
        return req.json()['data']['user']['repositories']['totalCount']
    elif count_type == 'stars':
        return sum(
            n['node']['stargazers']['totalCount']
            for n in req.json()['data']['user']['repositories']['edges']
        )


def recursive_loc(owner, repo_name, data, cache_comment,
                  addition_total=0, deletion_total=0, my_commits=0, cursor=None):
    query_count('recursive_loc')
    query = '''
    query ($repo_name: String!, $owner: String!, $cursor: String) {
        repository(name: $repo_name, owner: $owner) {
            defaultBranchRef {
                target {
                    ... on Commit {
                        history(first: 100, after: $cursor) {
                            totalCount
                            edges {
                                node {
                                    ... on Commit { committedDate }
                                    author { user { id } }
                                    deletions
                                    additions
                                }
                            }
                            pageInfo { endCursor hasNextPage }
                        }
                    }
                }
            }
        }
    }'''
    variables = {'repo_name': repo_name, 'owner': owner, 'cursor': cursor}
    req = requests.post(
        'https://api.github.com/graphql',
        json={'query': query, 'variables': variables},
        headers=HEADERS,
    )
    if req.status_code == 200:
        ref = req.json()['data']['repository']['defaultBranchRef']
        if ref is None:
            return 0
        return loc_counter_one_repo(
            owner, repo_name, data, cache_comment,
            ref['target']['history'],
            addition_total, deletion_total, my_commits,
        )
    force_close_file(data, cache_comment)
    if req.status_code == 403:
        raise Exception('Rate limited by GitHub anti-abuse system.')
    raise Exception('recursive_loc() failed with', req.status_code, req.text, QUERY_COUNT)


def loc_counter_one_repo(owner, repo_name, data, cache_comment,
                         history, addition_total, deletion_total, my_commits):
    for node in history['edges']:
        if node['node']['author']['user'] == OWNER_ID:
            my_commits += 1
            addition_total += node['node']['additions']
            deletion_total += node['node']['deletions']
    if not history['edges'] or not history['pageInfo']['hasNextPage']:
        return addition_total, deletion_total, my_commits
    return recursive_loc(
        owner, repo_name, data, cache_comment,
        addition_total, deletion_total, my_commits,
        history['pageInfo']['endCursor'],
    )


def loc_query(owner_affiliation, comment_size=0, force_cache=False, cursor=None, edges=[]):
    query_count('loc_query')
    query = '''
    query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
        user(login: $login) {
            repositories(first: 60, after: $cursor, ownerAffiliations: $owner_affiliation) {
                edges {
                    node {
                        ... on Repository {
                            nameWithOwner
                            defaultBranchRef {
                                target {
                                    ... on Commit { history { totalCount } }
                                }
                            }
                        }
                    }
                }
                pageInfo { endCursor hasNextPage }
            }
        }
    }'''
    variables = {'owner_affiliation': owner_affiliation, 'login': USER_NAME, 'cursor': cursor}
    req = simple_request(loc_query.__name__, query, variables)
    repos = req.json()['data']['user']['repositories']
    if repos['pageInfo']['hasNextPage']:
        edges += repos['edges']
        return loc_query(owner_affiliation, comment_size, force_cache,
                         repos['pageInfo']['endCursor'], edges)
    return cache_builder(edges + repos['edges'], comment_size, force_cache)


def cache_builder(edges, comment_size, force_cache, loc_add=0, loc_del=0):
    cached   = True
    filename = 'cache/' + hashlib.sha256(USER_NAME.encode()).hexdigest() + '.txt'
    try:
        with open(filename, 'r') as f:
            data = f.readlines()
    except FileNotFoundError:
        data = []
        if comment_size > 0:
            data = ['Cache line.\n'] * comment_size
        with open(filename, 'w') as f:
            f.writelines(data)

    if len(data) - comment_size != len(edges) or force_cache:
        cached = False
        flush_cache(edges, filename, comment_size)
        with open(filename, 'r') as f:
            data = f.readlines()

    cache_comment = data[:comment_size]
    data = data[comment_size:]

    for index, edge in enumerate(edges):
        repo_hash, commit_count, *_ = data[index].split()
        if repo_hash == hashlib.sha256(
                edge['node']['nameWithOwner'].encode()).hexdigest():
            try:
                live_count = edge['node']['defaultBranchRef']['target']['history']['totalCount']
                if int(commit_count) != live_count:
                    owner, repo_name = edge['node']['nameWithOwner'].split('/')
                    loc = recursive_loc(owner, repo_name, data, cache_comment)
                    data[index] = (
                        repo_hash + ' ' + str(live_count) + ' '
                        + str(loc[2]) + ' ' + str(loc[0]) + ' ' + str(loc[1]) + '\n'
                    )
            except TypeError:
                data[index] = repo_hash + ' 0 0 0 0\n'

    with open(filename, 'w') as f:
        f.writelines(cache_comment)
        f.writelines(data)

    for line in data:
        parts = line.split()
        loc_add += int(parts[3])
        loc_del += int(parts[4])
    return [loc_add, loc_del, loc_add - loc_del, cached]


def flush_cache(edges, filename, comment_size):
    with open(filename, 'r') as f:
        data = f.readlines()[:comment_size] if comment_size > 0 else []
    with open(filename, 'w') as f:
        f.writelines(data)
        for node in edges:
            f.write(hashlib.sha256(
                node['node']['nameWithOwner'].encode()).hexdigest() + ' 0 0 0 0\n')


def force_close_file(data, cache_comment):
    filename = 'cache/' + hashlib.sha256(USER_NAME.encode()).hexdigest() + '.txt'
    with open(filename, 'w') as f:
        f.writelines(cache_comment)
        f.writelines(data)


def commit_counter(comment_size):
    total = 0
    filename = 'cache/' + hashlib.sha256(USER_NAME.encode()).hexdigest() + '.txt'
    with open(filename, 'r') as f:
        data = f.readlines()[comment_size:]
    for line in data:
        total += int(line.split()[2])
    return total


def user_getter(username):
    query_count('user_getter')
    query = '''
    query($login: String!) {
        user(login: $login) { id createdAt }
    }'''
    req = simple_request(user_getter.__name__, query, {'login': username})
    return (
        {'id': req.json()['data']['user']['id']},
        req.json()['data']['user']['createdAt'],
    )


def follower_getter(username):
    query_count('follower_getter')
    query = '''
    query($login: String!) {
        user(login: $login) { followers { totalCount } }
    }'''
    req = simple_request(follower_getter.__name__, query, {'login': username})
    return int(req.json()['data']['user']['followers']['totalCount'])


def query_count(funct_id):
    global QUERY_COUNT
    QUERY_COUNT[funct_id] += 1


def perf_counter(funct, *args):
    start = time.perf_counter()
    result = funct(*args)
    return result, time.perf_counter() - start


def formatter(query_type, difference, funct_return=False, whitespace=0):
    print('{:<23}'.format('   ' + query_type + ':'), end='')
    if difference > 1:
        print('{:>12}'.format('%.4f' % difference + ' s '))
    else:
        print('{:>12}'.format('%.4f' % (difference * 1000) + ' ms'))
    if whitespace:
        return f"{'{:,}'.format(funct_return): <{whitespace}}"
    return funct_return

def generate_svg(filename, mode, age_data, commit_data, star_data,
                 repo_data, contrib_data, follower_data, loc_data):

    try:
        with open(PROFILE_IMAGE, 'rb') as f:
            img_b64 = base64.b64encode(f.read()).decode()
        ext  = PROFILE_IMAGE.rsplit('.', 1)[-1].lower()
        mime = 'image/jpeg' if ext in ('jpg', 'jpeg') else 'image/png'
        img_src  = f'data:{mime};base64,{img_b64}'
        has_image = True
    except FileNotFoundError:
        has_image = False
        img_src   = ''
        print(f'Warning: {PROFILE_IMAGE} not found. SVG will have no image.')

    if mode == 'dark':
        BG       = '#1e2030'
        LABEL    = '#e5a050'
        VALUE    = '#cdd6f4'
        HEADER   = '#89b4fa'
        SEP      = '#45475a'
        DOT      = '#585b70'
        SECTION  = '#cba6f7'
        PREFIX   = '#6c7086'
        LOC_ADD  = '#a6e3a1'
        LOC_DEL  = '#f38ba8'
        CONTRIB  = '#f9e2af'
    else:
        BG       = '#dce0e8'
        LABEL    = '#8c5e20'
        VALUE    = '#4c4f69'
        HEADER   = '#1e66f5'
        SEP      = '#9ca0b0'
        DOT      = '#9ca0b0'
        SECTION  = '#8839ef'
        PREFIX   = '#9ca0b0'
        LOC_ADD  = '#40a02b'
        LOC_DEL  = '#d20f39'
        CONTRIB  = '#df8e1d'

    W, H         = 960, 494
    IMG_X, IMG_Y = 18, 18
    IMG_W, IMG_H = 345, 458
    TX = 382
    LH = 19
    FS = 13
    FONT = (
        "font-family=\"'Courier New',Courier,monospace\" "
        f"font-size=\"{FS}\""
    )

    def e(s):
        return xml_escape(str(s))

    elements = []
    y = [50]

    def line(parts):
        spans = ''.join(
            f'<tspan fill="{c}">{e(s)}</tspan>'
            for s, c in parts
        )
        elements.append(
            f'<text x="{TX}" y="{y[0]}" {FONT}>{spans}</text>'
        )
        y[0] += LH

    def blank():
        elements.append(
            f'<text x="{TX}" y="{y[0]}" {FONT}>'
            f'<tspan fill="{PREFIX}">.</tspan></text>'
        )
        y[0] += LH

    def dots(label, col=30):
        n = col - len(f'. {label}: ')
        return '.' * max(1, n)

    def data_line(label, value, col=30):
        d = dots(label, col)
        line([
            ('. ', PREFIX),
            (label, LABEL),
            (': ', VALUE),
            (d + ' ', DOT),
            (value, VALUE),
        ])

    def section_header(title, width=62):
        dashes = '─' * max(1, width - len(title) - 3)
        line([(f'- {title} ', SECTION), (dashes, SEP)])

    hdr    = 'neel@sheth '
    dashes = '─' * max(1, 62 - len(hdr))
    line([(hdr, HEADER), (dashes, SEP)])

    data_line('OS',     OS_INFO)
    data_line('Uptime', age_data)
    data_line('Host',   HOST_INFO)
    data_line('Kernel', KERNEL_INFO)
    data_line('IDE',    IDE_INFO)
    blank()

    data_line('Languages.Programming', LANG_PROG, col=34)
    data_line('Languages.Computer',    LANG_COMP, col=34)
    data_line('Languages.Real',        LANG_REAL, col=34)
    blank()

    data_line('Hobbies.Software', HOBBY_SW)
    data_line('Hobbies.Hardware', HOBBY_HW)
    blank()

    section_header('Contact')
    data_line('Email',    EMAIL)
    data_line('LinkedIn', LINKEDIN)
    data_line('Discord',  DISCORD)
    blank()

    section_header('GitHub Stats')

    r_val = str(repo_data)
    c_val = str(contrib_data)
    s_val = f'{star_data:,}' if isinstance(star_data, int) else str(star_data)
    r_dots = '.' * max(1, 6  - len(r_val))
    s_dots = '.' * max(1, 14 - len(s_val))
    line([
        ('. ', PREFIX),
        ('Repos', LABEL), (': ', VALUE),
        (r_dots + ' ', DOT),
        (r_val, VALUE),
        (' {Contributed: ', CONTRIB),
        (c_val, CONTRIB),
        ('} | ', VALUE),
        ('Stars', LABEL), (': ', VALUE),
        (s_dots + ' ', DOT),
        (s_val, VALUE),
    ])

    cm_val = f'{commit_data:,}' if isinstance(commit_data, int) else str(commit_data)
    fl_val = str(follower_data)
    cm_dots = '.' * max(1, 22 - len(cm_val))
    fl_dots = '.' * max(1, 9  - len(fl_val))
    line([
        ('. ', PREFIX),
        ('Commits', LABEL), (': ', VALUE),
        (cm_dots + ' ', DOT),
        (cm_val, VALUE),
        (' | ', VALUE),
        ('Followers', LABEL), (': ', VALUE),
        (fl_dots + ' ', DOT),
        (fl_val, VALUE),
    ])

    loc_total = loc_data[2] if len(loc_data) > 2 else '0'
    loc_add   = loc_data[0]
    loc_del   = loc_data[1]
    line([
        ('. ', PREFIX),
        ('Lines of Code', LABEL), (': ', VALUE),
        (str(loc_total), VALUE),
        (' ( ', VALUE),
        (str(loc_add), LOC_ADD),
        ('++,  ', VALUE),
        (str(loc_del), LOC_DEL),
        ('-- )', VALUE),
    ])

    clip = (
        f'<clipPath id="imgclip">'
        f'<rect x="{IMG_X}" y="{IMG_Y}" width="{IMG_W}" '
        f'height="{IMG_H}" rx="8"/>'
        f'</clipPath>'
    )

    img_el = (
        f'<image href="{img_src}" '
        f'x="{IMG_X}" y="{IMG_Y}" '
        f'width="{IMG_W}" height="{IMG_H}" '
        f'preserveAspectRatio="xMidYMid meet" '
        f'clip-path="url(#imgclip)"/>'
        if has_image else ''
    )

    text_block = '\n  '.join(elements)

    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}"
     xmlns="http://www.w3.org/2000/svg"
     xmlns:xlink="http://www.w3.org/1999/xlink">
  <defs>{clip}</defs>
  <rect width="{W}" height="{H}" rx="10" fill="{BG}"/>
  {img_el}
  {text_block}
</svg>'''

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(svg)
    print(f'  ✓ Written {filename}')

if __name__ == '__main__':
    print('Calculation times:')

    user_data, user_time = perf_counter(user_getter, USER_NAME)
    OWNER_ID, acc_date = user_data
    formatter('account data', user_time)

    age_data,    age_time    = perf_counter(daily_readme, BIRTHDAY)
    formatter('age', age_time)

    total_loc, loc_time = perf_counter(
        loc_query, ['OWNER', 'COLLABORATOR', 'ORGANIZATION_MEMBER'], 7)
    formatter('LOC (cached)' if total_loc[-1] else 'LOC (no cache)', loc_time)

    commit_data,   commit_time   = perf_counter(commit_counter, 7)
    star_data,     star_time     = perf_counter(graph_repos_stars, 'stars', ['OWNER'])
    repo_data,     repo_time     = perf_counter(graph_repos_stars, 'repos', ['OWNER'])
    contrib_data,  contrib_time  = perf_counter(
        graph_repos_stars, 'repos', ['OWNER', 'COLLABORATOR', 'ORGANIZATION_MEMBER'])
    follower_data, follower_time = perf_counter(follower_getter, USER_NAME)

    for i in range(len(total_loc) - 1):
        total_loc[i] = '{:,}'.format(total_loc[i])

    print('\nGenerating SVGs...')
    generate_svg('dark_mode.svg',  'dark',  age_data, commit_data, star_data,
                 repo_data, contrib_data, follower_data, total_loc[:-1])
    generate_svg('light_mode.svg', 'light', age_data, commit_data, star_data,
                 repo_data, contrib_data, follower_data, total_loc[:-1])

    print('\nTotal GitHub GraphQL API calls:', sum(QUERY_COUNT.values()))
    for fn, count in QUERY_COUNT.items():
        print(f'   {fn:<28}: {count}')