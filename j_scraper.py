from urllib.request import urlopen
from bs4 import BeautifulSoup
import re

# expects 
def parse_score(row):
    """
    Expects <td class = 'score_positive'> $XX,XXX <\td>
    """
    score = re.sub('\$|,','',row.text)
    if row.attrs['class'] == 'score_negative':
        score = '-' + score
    return score

def find_answer(clue):
    return clue.findNext('div').get('onmouseover')
    

def parse_jeopardy_questions(url_string):
    html = urlopen(url_string)
    parsed_html = BeautifulSoup(html,'html5lib')
    
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
            answer_text = BeautifulSoup(find_answer(clue)).find('em',{'class':'correct_response'}).text
            answer_id = re.search('clue_D?J_[0-9]_[0-9]',find_answer(clue)).group()
            answers[answer_id] = answer_text
        except:
            pass
    # need final jeopardy answer
    
    fj_div = BeautifulSoup(find_answer(parsed_html.find('table',{'class':'final_round'})),'html5')
    answers['clue_FJ'] = fj_div.find('em').text
    
    return categories,clues_dict, answers
    
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
            
        
def get_fj_results(url_string):
    html = urlopen(url_string)
    parsed_html = BeautifulSoup(html,'html5lib')
    
    # table of scores going into final jeopardy
    dj_table = parsed_html.find('div',{'id':'double_jeopardy_round'}).\
                find('h3').find_next_sibling()
    player_names = [child.text for child in dj_table.tr.findChildren()]
    dj_scores = [parse_score(row) for row in dj_table.tr.find_next_sibling().findChildren()]
    
    # parsing final jeopary wagers
    fj_table = parsed_html.find('div',{'id':'final_jeopardy_round'}).\
                find('td',{'class':"category"}).findChild()
    table = BeautifulSoup(fj_table.get('onmouseover'),'html5lib').\
            body.find('table').find_next()
    contestants = []
    fj_wagers = []
    fj_correct = []
    for row in table.findAll('td'):
        test = row.attrs
        if test == {}:
            fj_wagers.append(re.sub('\$|,','',row.text))
        elif test.get('class') == ['wrong']:
            contestants.append(row.text)
            fj_correct.append(False)
        elif test.get('class') == ['right']:
            contestants.append(row.text)
            fj_correct.append(True)
    
    dj = dict(zip(player_names,dj_scores))
    for contestant,wager,correct in zip(contestants,fj_wagers,fj_correct):
        dj[contestant] = [dj[contestant]] + [wager,correct]
    return dj

def get_links(url):
    html = urlopen('http://j-archive.com/showseason.php?season=33')
    parsed_html = BeautifulSoup(html,'html5lib')
    game_links = 

parse_jeopardy_game('http://www.j-archive.com/showgame.php?game_id=5599')
    
        
    