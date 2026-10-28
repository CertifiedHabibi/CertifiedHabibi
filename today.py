import datetime
import base64
import os
import time
import hashlib
import struct
import textwrap
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

OS_INFO     = 'Windows 11, Android 14'
HOST_INFO   = 'MIT World Peace University, Pune'
KERNEL_INFO = 'Cloud Computing Student'
IDE_INFO    = 'WebStorm, PyCharm, Rider, VSCode, VS'
LANG_PROG   = 'Python, JavaScript, C++, C#, Lua'
LANG_COMP   = 'HTML, CSS, JSON, LaTeX, YAML'
LANG_REAL   = 'English, Hindi, Gujarati'
HOBBY_SW    = 'Game Modding, Pixel Art'
HOBBY_HW    = 'Violin, Squash, Table Tennis'
EMAIL       = 'fxswift2610@gmail.com'
LINKEDIN    = 'CertifiedHabibi'
DISCORD     = 'certified._.habibi'


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


def graph_repos_stars(count_type, owner_affiliation, cursor=None, total=0):
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
    data = req.json()['data']['user']['repositories']
    if count_type == 'repos':
        return data['totalCount']
    elif count_type == 'stars':
        total += sum(
            n['node']['stargazers']['totalCount']
            for n in data['edges']
            if n['node'] is not None
        )
        if data['pageInfo']['hasNextPage']:
            return graph_repos_stars(count_type, owner_affiliation,
                                     data['pageInfo']['endCursor'], total)
        return total


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
        data = ['Cache line.\n'] * comment_size if comment_size > 0 else []
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


FONT_FILE = 'assets/PressStart2PFont/PressStart2P.ttf'


def png_size(path):
    with open(path, 'rb') as f:
        head = f.read(24)
    if head[:8] == b'\x89PNG\r\n\x1a\n':
        return struct.unpack('>II', head[16:24])
    return None


def generate_svg(filename, mode, age_data, commit_data, star_data,
                 repo_data, contrib_data, follower_data, loc_data):
    try:
        with open(PROFILE_IMAGE, 'rb') as f:
            raw = f.read()
        ext     = PROFILE_IMAGE.rsplit('.', 1)[-1].lower()
        mime    = 'image/jpeg' if ext in ('jpg', 'jpeg') else 'image/png'
        img_src = f'data:{mime};base64,{base64.b64encode(raw).decode()}'
        img_w, img_h = png_size(PROFILE_IMAGE) or (4, 5)
        has_image = True
    except FileNotFoundError:
        has_image, img_src, img_w, img_h = False, '', 4, 5
        print(f'Warning: {PROFILE_IMAGE} not found, SVG will render without image.')

    try:
        with open(FONT_FILE, 'rb') as f:
            font_b64 = base64.b64encode(f.read()).decode()
        font_css = (
            "@font-face{font-family:'PS2P';"
            f"src:url(data:font/woff;base64,{font_b64}) format('woff');}}"
        )
    except FileNotFoundError:
        font_css = ''
        print(f'Warning: {FONT_FILE} not found, falling back to monospace.')

    if mode == 'dark':
        BG, BORDER   = '#22272e', '#373e47'
        LABEL, VALUE = '#e6943a', '#cdd9e5'
        HEADER       = '#e6943a'
        SEP, DOT     = '#444c56', '#545d68'
        SECTION      = '#cdd9e5'
        PREFIX       = '#768390'
        LOC_ADD, LOC_DEL, CONTRIB = '#57ab5a', '#e5534b', '#e3b341'
    else:
        BG, BORDER   = '#ffffff', '#d0d7de'
        LABEL, VALUE = '#953800', '#24292f'
        HEADER       = '#953800'
        SEP, DOT     = '#d0d7de', '#afb8c1'
        SECTION      = '#24292f'
        PREFIX       = '#57606a'
        LOC_ADD, LOC_DEL, CONTRIB = '#1a7f37', '#cf222e', '#9a6700'

    FS, LH, GAP, PAD = 10, 18, 10, 26
    VAL_COL, MAX_VAL = 15, 32
    MAX_IMG_W        = 380
    GUTTER           = 28
    TEXT_W           = (VAL_COL + MAX_VAL) * FS

    FONT = (
        "font-family=\"'PS2P','Courier New',Courier,monospace\" "
        f'font-size="{FS}" xml:space="preserve"'
    )

    def e(s):
        return xml_escape(str(s))

    texts, rules = [], []
    y = [PAD + FS + 2]

    def text_line(parts, indent=0):
        spans = ''.join(f'<tspan fill="{c}">{e(s)}</tspan>' for s, c in parts)
        texts.append((indent * FS, y[0], spans))
        y[0] += LH

    def header(title, color):
        rules.append(((len(title) + 1) * FS, y[0] - FS // 2 + 1))
        text_line([(title, color)])

    def row(label, value):
        parts = [(value, VALUE)] if isinstance(value, str) else value
        used  = 2 + len(label) + 1
        dots  = '.' * max(1, VAL_COL - used - 2)
        head  = [('. ', PREFIX), (label, LABEL), (':', VALUE), (' ' + dots + ' ', DOT)]
        if len(parts) > 1:
            text_line(head + parts)
            return
        chunks = textwrap.wrap(parts[0][0], MAX_VAL) or ['']
        text_line(head + [(chunks[0], parts[0][1])])
        for chunk in chunks[1:]:
            text_line([(chunk, parts[0][1])], indent=VAL_COL)

    header('neel@sheth', HEADER)
    row('OS',     OS_INFO)
    row('Uptime', age_data)
    row('Host',   HOST_INFO)
    row('Kernel', KERNEL_INFO)
    row('IDE',    IDE_INFO)
    y[0] += GAP

    header('Languages', SECTION)
    row('Prog',   LANG_PROG)
    row('Markup', LANG_COMP)
    row('Spoken', LANG_REAL)
    y[0] += GAP

    header('Hobbies', SECTION)
    row('Software', HOBBY_SW)
    row('Hardware', HOBBY_HW)
    y[0] += GAP

    header('Contact', SECTION)
    row('Email',    EMAIL)
    row('LinkedIn', LINKEDIN)
    row('Discord',  DISCORD)
    y[0] += GAP

    header('GitHub Stats', SECTION)
    s_val  = f'{star_data:,}'   if isinstance(star_data, int)   else str(star_data)
    cm_val = f'{commit_data:,}' if isinstance(commit_data, int) else str(commit_data)
    row('Repos', [(str(repo_data), VALUE),
                  ('  {Contrib: ', CONTRIB), (str(contrib_data), CONTRIB), ('}', CONTRIB)])
    row('Stars',     s_val)
    row('Commits',   cm_val)
    row('Followers', str(follower_data))
    loc_total = loc_data[2] if len(loc_data) > 2 else '0'
    row('LOC', [(str(loc_total), VALUE), (' (', VALUE),
                (f'{loc_data[0]}++', LOC_ADD), (' ', VALUE),
                (f'{loc_data[1]}--', LOC_DEL), (')', VALUE)])

    H = y[0] - LH + 6 + PAD

    box_h = H - 2 * PAD
    if has_image:
        ratio = min(1.0, max(0.75, img_w / img_h))
        box_w = min(MAX_IMG_W, round(box_h * ratio))
        TX    = PAD + box_w + GUTTER
    else:
        box_w, TX = 0, PAD
    W = TX + TEXT_W + PAD

    img_el = ''
    if has_image:
        img_el = (
            f'<clipPath id="imgclip"><rect x="{PAD}" y="{PAD}" width="{box_w}" '
            f'height="{box_h}" rx="6"/></clipPath>'
            f'<image href="{img_src}" x="{PAD}" y="{PAD}" width="{box_w}" '
            f'height="{box_h}" preserveAspectRatio="xMidYMid slice" '
            f'style="image-rendering:pixelated" clip-path="url(#imgclip)"/>'
        )

    body = [
        f'<text x="{TX + dx}" y="{ty}" {FONT}>{spans}</text>'
        for dx, ty, spans in texts
    ]
    body += [
        f'<rect x="{TX + dx}" y="{ry}" width="{TEXT_W - dx}" height="2" fill="{SEP}"/>'
        for dx, ry in rules
    ]
    body = '\n  '.join(body)

    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        'xmlns="http://www.w3.org/2000/svg">\n'
        f'  <style>{font_css} text{{text-rendering:optimizeLegibility}}</style>\n'
        f'  <rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="10" '
        f'fill="{BG}" stroke="{BORDER}"/>\n'
        f'  {img_el}\n'
        f'  {body}\n'
        '</svg>'
    )

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(svg)
    print(f'  ✓ Written {filename}')


if __name__ == '__main__':
    print('Calculation times:')

    user_data, user_time = perf_counter(user_getter, USER_NAME)
    OWNER_ID, acc_date = user_data
    formatter('account data', user_time)

    age_data, age_time = perf_counter(daily_readme, BIRTHDAY)
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