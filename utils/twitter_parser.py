from bs4 import BeautifulSoup
import re

def parse_twitter_html(html_content, target_user, original_url=None):
    """
    Playwright가 렌더링한 HTML을 파싱하여 트윗 본문, 미디어, 실제 유저명을 추출합니다.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    real_user = None
    
    # 1. URL에서 유저명 추출 (가능한 경우)
    if original_url:
        match = re.search(r'x\.com/([^/]+)/status/\d+', original_url)
        if match and match.group(1) != 'i' and match.group(1) != 'None':
            real_user = match.group(1)
            
    # 2. HTML 내 User-Name에서 추출
    if not real_user:
        user_name_divs = soup.find_all('div', attrs={"data-testid": "User-Name"})
        if user_name_divs:
            for link in user_name_divs[0].find_all('a', href=True):
                href = link['href']
                if href and href != "/" and "/status" not in href:
                    real_user = href.replace("/", "")
                    break
                    
    if not real_user:
        real_user = target_user

    tweet_texts = []
    tweet_media = set()
    
    articles = soup.find_all('article', attrs={"data-testid": "tweet"})
    for i, article in enumerate(articles):
        # 작성자 확인 로직
        is_author = False
        links = article.find_all('a', href=True)
        for link in links:
            href = link['href']
            if href.lower() == f"/{real_user.lower()}":
                is_author = True
                break
                
        # 메인 트윗(i=0)인 경우 텍스트가 있으면 무조건 수집 (작성자 확인 실패 대비)
        if not is_author:
            if i == 0:
                text_el = article.find('div', attrs={"data-testid": "tweetText"})
                if text_el:
                    is_author = True
            else:
                continue

        # 텍스트 추출 (첫 번째 tweetText)
        text_els = article.find_all('div', attrs={"data-testid": "tweetText"})
        article_body = ""
        if text_els:
            # BeautifulSoup의 get_text는 자식 요소의 텍스트를 모두 결합
            article_body = text_els[0].get_text(separator='\n').strip()
            
        if article_body and article_body not in tweet_texts:
            tweet_texts.append(article_body)
            
        # 미디어 추출
        imgs = article.find_all('img', src=re.compile(r'media'))
        for img in imgs:
            src = img.get('src')
            if src:
                clean_src = f"https://wsrv.nl/?url={src.split('?')[0]}"
                tweet_media.add(clean_src)

    full_text = "\n\n---\n\n".join(tweet_texts)
    return full_text, list(tweet_media), real_user
