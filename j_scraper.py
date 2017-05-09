from urllib.request import urlopen
from bs4 import BeautifulSoup
import re
import pandas as pd
import sqlalchemy
import numpy as np

def parse_score(row):
    """
    Expects <td class = 'score_positive'> $XX,XXX <\td>
    """
    score = re.sub('\$|,','',row.text)
    if row.attrs['class'] == 'score_negative':
        score = '-' + score
    return score

def find_answer(clue):
    """
    Finds answer in 'onmouseover' 
    """
    return clue.findNext('div').get('onmouseover')

def extract_player_name(text, player_nickname):
    """
    Extract name from player introduction text 
    """
    name = text.split(',')[0]
    lastname = name.replace(player_nickname,'').strip()
    return player_nickname,lastname

def extract_playerid(person):
    """
    Extract player id from player link in introduction text
    """
    link = person.find('a')['href']
    return link[link.find('=')+1:]

def extract_hometown(text):
    """
    Extract town and state from introduction text
    """
    town_state = [x.strip() for x in text.split('from')]
    # to guard against the case the announcer says from in the intro
    try:

        if len(town_state) == 3:
            town_state = [x.strip() for x in town_state[2].split(',')]
        else:
            town_state = [x.strip() for x in town_state[1].split(',')]
        if re.search('\(.*$',town_state[1]):
            town_state[1] = re.sub('\(.*$' ,'', town_state[1])

    except:
        return [np.nan,np.nan]

    # return first two elements because if returning champion cash winnings will also have a comma,
    # so there's extra junk after we split on ','
    return town_state[0:2]

def extract_occupation(text):
    """
    Extract occupation from introduction text
    """
    occupation = text.split(',')[1]
    return occupation[1:occupation.find('from')]

def map_to_value(round,row_index):
    """
    Map the question row index to it's corresponding value
    """
    values = [200,400,600,800,1000]
    if round == 'J':
        return values[int(row_index) - 1]
    else:
        return 2*values[int(row_index) - 1]

def map_to_category(round,categories,column_index):
    """
    Map question column index to the appropriate category 
    """
    offset = 0 if round == 'J' else 6
    return categories[offset + int(column_index) - 1]
    
def parse_contestants_table(parsed_html):
    """
    Extract player demographics table. Create 'contestants' table in postgresql for a given game
    """
    contestant_tags = parsed_html.findAll('p', {'class': 'contestants'})
    player_nicknames = [x.text for x in parsed_html.findAll('td',{'class': 'score_player_nickname'})][0:3]
    contestants = []
    for i,person in enumerate(contestant_tags):
        person_id = extract_playerid(person)
        player_name = extract_player_name(person.text, player_nicknames[2 - i])
        hometown = extract_hometown(person.text)
        occupation = extract_occupation(person.text)
        contestants.append({'player_id' : person_id, 'player_first_name' : player_name[0].strip(),
                            'player_last_name' : player_name[1].strip(), 'occupation' : occupation.strip(),
                            'hometown_city' : hometown[0], 'hometown_state' : hometown[1]})
    return contestants

def parse_player_locations(parsed_html,game_id):
    """
    Map the player names to the seating arrangement table. Creates player_locations table postgresql
    """
    contestant_tags = parsed_html.findAll('p', {'class': 'contestants'})
    ids = [extract_playerid(person) for person in contestant_tags]
    return [{'game_id': game_id,'player_id': ids[0], 'seat_location': 'right'},
            {'game_id': game_id, 'player_id': ids[1], 'seat_location': 'middle'},
            {'game_id': game_id, 'player_id': ids[2], 'seat_location': 'returning_champ'}]

def parse_game_trend_table(parsed_html,contestants_table,contestants_locations,game_id):
    """
    Creates game_trends table in postgresql 
    """
    c_table = pd.DataFrame(contestants_table)
    l_table = pd.DataFrame(contestants_locations)
    tab = c_table[['player_id','player_first_name']].merge(l_table[['player_id','seat_location']], on = 'player_id')
    df = []
    clues = parsed_html.findAll('td',{'class' : 'clue'})
    for clue in clues:

        # if the question doesn't have an id, the contestants didn't have time to select it on air
        try:
            id = clue.find('td', {'class' : 'clue_text'}).get('id')
        except AttributeError:
            continue
        row_dict = {}

        # skip FJ since handled by parse_final_results function
        if id == 'clue_FJ':
            continue
        else:

            formatted_answer = BeautifulSoup(find_answer(clue), 'html5')

            # If no one answers the question correctly, it's a triple stumper
            try:
                correct_respondent = formatted_answer.find('td', {'class': 'right'}).text
                row_dict['correct_respondent'] = list(tab['seat_location'].loc[tab['player_first_name'] == correct_respondent])[0]
            except AttributeError:
                row_dict['correct_respondent'] = 'triple_stumper'

            tokens = id.split('_')
            value = map_to_value(tokens[1],tokens[3])
            index = clue.findChild('td',{'class': 'clue_order_number'}).find('a').text
            row_dict['game_id'] = game_id
            row_dict['round'] = id.split('_')[1]
            row_dict['question_index'] = int(index)
            row_dict['row'] = int(tokens[3])
            row_dict['column'] = int(tokens[2])
            row_dict['value'] = value
            df.append(row_dict)

    df = pd.DataFrame(df)

    # question index in website starts at 1 in each round
    df['question_index'].loc[df['round'] == 'DJ'] = \
                    df['question_index'].loc[df['round'] == 'DJ'] + df['question_index'].loc[df['round'] == 'J'].max()
    return df.sort_values(by = 'question_index')

def parse_jeopardy_questions(parsed_html,game_id):
    """
    Parse all question and answers (including Final Jeopardy) from the game board. Creates questions table in postgresql
    """
    categories = parsed_html.findAll('td',{'class' : 'category_name'})
    categories = [cat.text for cat in categories]
    
    if len(categories) < 10:
        return None, None
    
    clues = parsed_html.findAll('td',{'class':'clue_text'})
    clue_ids = [clue.get('id') for clue in clues]
    clue_texts = [clue.text for clue in clues]
    clues_dict = dict(zip(clue_ids,clue_texts))
    
    clues = parsed_html.findAll('td',{'class':'clue'})
    
    answers = {}
    for i,clue in enumerate(clues):
        try:
            formatted_answer = BeautifulSoup(find_answer(clue),'html5')
            answer_text = formatted_answer.find('em',{'class' : 'correct_response'}).text
            answer_id = re.search('clue_D?J_[0-9]_[0-9]',find_answer(clue)).group()
            answers[answer_id] = answer_text
        except:
            pass

    # need final jeopardy answer
    fj_div = BeautifulSoup(find_answer(parsed_html.find('table',{'class':'final_round'})),'html5')
    answers['clue_FJ'] = fj_div.find('em').text

    question_list = []
    for id in answers.keys():
        if id == 'clue_FJ':
            question_list.append({'game_id' : game_id, 'round' : 'final', 'category' : 'final',
                                   'value' : -1, 'question_text' : clues_dict[id], 'answer' : answers[id]})
        else:
            tokens = id.split('_')
            value = map_to_value(tokens[1],tokens[3])
            category = map_to_category(tokens[1],categories,tokens[2])
            question_list.append({'game_id' : game_id, 'round' : tokens[1], 'row' : int(tokens[3]),
                                 'column' : int(tokens[2]),'category' : category,
                                  'value' : value, 'question_text' : clues_dict[id], 'answer' : answers[id]})
    return question_list

def get_fj_results(parsed_html, game_id):
    """
    Extract wagers and coryat scores to get end_game results. Used in end_games table in postgresql
    """

    # table of scores going into final jeopardy
    dj_table = parsed_html.find('div', {'id': 'double_jeopardy_round'}). \
        find('h3').find_next_sibling()
    player_names = [child.text for child in dj_table.tr.findChildren()]
    dj_scores = [parse_score(row) for row in dj_table.tr.find_next_sibling().findChildren()]

    # parsing final jeopardy wagers
    fj_table = parsed_html.find('div', {'id': 'final_jeopardy_round'}). \
        find('td', {'class': "category"}).findChild()
    table = BeautifulSoup(fj_table.get('onmouseover'), 'html5lib'). \
        body.find('table').find_next()
    contestants = []
    fj_wagers = []
    fj_correct = []

    # wagers are listed in ascending order of score
    for row in table.findAll('td'):
        test = row.attrs
        if test == {}:
            fj_wagers.append(re.sub('\$|,', '', row.text))
        elif test.get('class') == ['wrong']:
            contestants.append(row.text)
            fj_correct.append(False)
        elif test.get('class') == ['right']:
            contestants.append(row.text)
            fj_correct.append(True)

    contestant_names = []
    coryat_scores =[]
    coryat_table  = parsed_html.find('a',text = 'Coryat scores').parent.find_next_sibling('table')
    for row in coryat_table.findAll('td'):
        if row.attrs.get('class') == ['score_player_nickname']:
            contestant_names.append(row.text)
        elif row.attrs.get('class') == ['score_positive']:
            coryat_scores.append(re.sub('\$|,', '', row.text))
        elif row.attrs.get('class') == ['score_negative']:
            coryat_scores.append(re.sub('\$|,', '', row.text))

    dj = dict(zip(player_names, dj_scores))
    fj_scores = dict(zip(contestants, zip(fj_wagers, fj_correct)))
    coryat = dict(zip(contestant_names,coryat_scores))
    fj_list = []
    positions = dict(zip(player_names, ['returning_champion', 'middle', 'right']))
    for contestant in coryat:
        fj_list.append({'game_id': game_id, 'position': positions[contestant],
                        'dj_score': float(dj[contestant]),
                        'wager': float(fj_scores.get(contestant,(np.nan,np.nan))[0]),
                        'correct': fj_scores.get(contestant,(np.nan,np.nan))[1],
                        'coryat_score' : float(coryat[contestant])})
    return fj_list

def parse_game(game,season):
    print(season)
    con = sqlalchemy.create_engine('postgresql://localhost/jeopardy', client_encoding='utf8')
    game_link = game.find_next('a').get('href')
    game_id = game_link[game_link.find('=')+ 1:]

    games_seen = pd.read_sql('select distinct game_id from trend',con)

    if game_id in list(games_seen['game_id']):
        print('game ' + game_id + 'already seen')
        return None

    print(game_id)
    try:
        # parse data and create dataframes
        game_html = BeautifulSoup(urlopen(game_link), 'html5lib')
        contestants = pd.DataFrame(parse_contestants_table(game_html))
        locations = pd.DataFrame(parse_player_locations(game_html, game_id))
        questions = pd.DataFrame(parse_jeopardy_questions(game_html, game_id))
        final_results = pd.DataFrame(get_fj_results(game_html, game_id))
        trend = parse_game_trend_table(game_html, contestants, locations, game_id)

        # add season variable, last minute addition
        locations['season'] = season
        questions['season'] = season
        final_results['season'] = season
        trend['season'] = season

        # reorder columns
        contestants = contestants[['player_id', 'player_first_name', 'player_last_name',
                                   'hometown_city', 'hometown_state', 'occupation']]
        questions = questions[['game_id', 'season', 'round', 'row',
                               'column', 'category', 'value', 'question_text']]
        final_results = final_results[['game_id', 'season', 'position', 'dj_score',
                                       'wager', 'correct', 'coryat_score']]
        trend = trend[['game_id', 'season', 'question_index', 'round',
                       'row', 'column', 'correct_respondent', 'value']]
        contestants.to_sql('contestants', con, index = False, if_exists = 'append')
        locations.to_sql('locations', con, index = False, if_exists = 'append')
        questions.to_sql('questions', con, index = False, if_exists = 'append')
        final_results.to_sql('final_results', con, index = False, if_exists = 'append')
        trend.to_sql('trend', con, index = False, if_exists = 'append')

    except:
        pass

def parse_season(url_string, season):
    season = int(season)
    html = urlopen(url_string)
    parsed_html = BeautifulSoup(html, 'html5lib')
    games = parsed_html.find_all('tr')
    for game in games:
        parse_game(game,season)

def get_season_links(url = 'http://j-archive.com/listseasons.php'):
    html = urlopen(url)
    parsed_html = BeautifulSoup(html,'html5lib')
    season_links = [link.get('href') for link in parsed_html.findAll('a')]
    season_links = list(filter(re.compile('^showseason.php\?season=').match,season_links))
    for season in season_links:
        season = 'http://j-archive.com/' + season
        season_number = season[season.find('=')+1:]
        parse_season(season,season_number)
        if int(season_number) < 17:
            break


