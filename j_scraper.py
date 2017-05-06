from urllib.request import urlopen
from bs4 import BeautifulSoup
import re
import pandas as pd

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
    :param clue html
    :return: 
    """
    return clue.findNext('div').get('onmouseover')

def extract_player_name(text):
    """
    Extract name from player introduction text 
    """
    return text.split(',')[0].split(' ')

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
    town_state = text.split('from')[1].split(',')
    town_state[1] = town_state[1].split(' ')[1]
    return town_state

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
    contestants = []
    for person in contestant_tags:
        person_id = extract_playerid(person)
        player_name = extract_player_name(person.text)
        hometown = extract_hometown(person.text)
        occupation = extract_occupation(person.text)
        contestants.append({'player_id' : person_id, 'player_first_name' : player_name[0].strip(),
                            'player_last_name' : player_name[1].strip(), 'occupation' : occupation.strip(),
                            'hometown_city' : hometown[0].strip(), 'hometown_state' : hometown[1].strip()})
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
    Creates postgresql in 
    """
    c_table = pd.DataFrame(contestants_table)
    l_table = pd.DataFrame(contestants_locations)
    tab = c_table[['player_id','player_first_name']].merge(l_table[['player_id','seat_location']], on = 'player_id')
    df = []
    clues = parsed_html.findAll('td',{'class' : 'clue'})
    for i,clue in enumerate(clues):
        id = clue.find('td', {'class' : 'clue_text'}).get('id')
        row_dict = {}

        # skip FJ since all players get to answer
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
            row_dict['row'] = tokens[3]
            row_dict['column'] = tokens[2]
            row_dict['value'] = value
            df.append(row_dict)

    return pd.DataFrame(df).sort('question_index')

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
            question_list.append({'game_id' : game_id, 'round' : tokens[1], 'row' : tokens[3],
                                 'column' : tokens[2],'category' : category,
                                  'value' : value, 'question_text' : clues_dict[id], 'answer' : answers[id]})
    return question_list


def get_fj_results(parsed_html):
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
            coryat_scores.append(row.text)

    dj = dict(zip(player_names, dj_scores))
    coryat = dict(zip(contestant_names,coryat_scores))
    fj_list = []
    positions = dict(zip(player_names, ['returning_champion', 'middle', 'right']))
    for contestant, wager, correct in zip(contestants, fj_wagers, fj_correct):
        fj_list.append({'game_id': game_id, 'position': positions[contestant],
                        'dj_score': dj[contestant],
                        'wager': wager, 'correct': correct,
                        'coryat_score' : coryat[contestant]})
    return fj_list


def parse_season(url_string):
    season = {}
    html = urlopen(url_string)
    parsed_html = BeautifulSoup(html,'html5lib')
    games = parsed_html.find_all('tr')
    for game in games:
        game_link = game.find_next('a').get('href')
        game_id = game_link[game_link.find('=')+ 1:]
        try:
            season[game_id] = parse_jeopardy_questions(game_link)
        except TypeError:
            pass
    return season




def get_links(url):
    html = urlopen('http://j-archive.com/showseason.php?season=33')
    parsed_html = BeautifulSoup(html,'html5lib')
    game_links = 

parse_jeopardy_game('http://www.j-archive.com/showgame.php?game_id=5599')
    
        
    