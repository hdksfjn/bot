import asyncio
import time

import pymongo
import requests
from io import BytesIO
from config import TOKEN
from bs4 import BeautifulSoup
from aiogram import Bot, types
from aiogram.dispatcher import Dispatcher
from aiogram.utils import executor, exceptions

client = pymongo.MongoClient('localhost', 27017)
db = client['UkrInform']
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)


async def check_subs(user_id):
    user_data = db.users.find_one({'user_id': user_id})
    if user_data is not None:
        return user_data


async def subscribe_news(user_id):
    user_subs = await check_subs(user_id)
    if user_subs is None:
        db.users.insert_one({'user_id': user_id, 'last_article': None})
        return True
    return False


async def unsubscribe_new(user_id):
    user_subs = await check_subs(user_id)
    if user_subs is not None:
        db.users.delete_one({'user_id': user_id})
        return True
    return False


async def update_last_article(article_url, user_id):
    new_value = {"$set": {'last_article': article_url}}
    db.users.update_one({'user_id': user_id}, new_value)


async def parser():
    URL = "https://www.ukrinform.ua"

    page = requests.get(URL + '/block-lastnews')
    soup = BeautifulSoup(page.content, "html.parser")

    post = soup.find("div", class_="rest")
    image_url = post.find('a').find('img')['src']
    article_url = URL + post.find('a')['href']
    article_header = post.find('div').find('a').text
    text = post.find('p').find('p')
    text = text.text if text is not None else ''

    data = {'image_url': image_url, 'article_url': article_url, 'article_header': article_header, 'text': text}
    db_data = db.articles.find_one(data)
    if db_data is None:
        db.articles.insert_one(data)


async def post_builder(post_data):
    img = requests.get(post_data['image_url']).content
    post_body = f"<b>{post_data['article_header']}</b>\n\n" \
                f"{post_data['text']}\n\n" \
                f"<a href='{post_data['article_url']}'>Детальніше</a>"

    return img, post_body


async def send_messages():
    db_data = db.articles.find_one(sort=[('_id', pymongo.DESCENDING)])
    img, post_body = await post_builder(db_data)

    for user in db.users.find():
        if user['last_article'] is None or user['last_article'] != db_data['article_url']:
            try:
                await bot.send_photo(chat_id=user['user_id'], photo=BytesIO(img), caption=post_body, parse_mode='HTML')
                await update_last_article(db_data['article_url'], user['user_id'])
            except exceptions.BotBlocked:
                db.users.delete_one({'user_id': user['user_id']})


async def parser_task():
    while True:
        await parser()
        await asyncio.sleep(3)


async def send_messages_task():
    while True:
        await send_messages()
        await asyncio.sleep(1)


async def on_startup(_):
    asyncio.create_task(parser_task())
    asyncio.create_task(send_messages_task())


@dp.message_handler(commands=['start'])
async def process_start_command(message: types.Message):
    if await subscribe_news(message.chat.id):
        await bot.send_message(message.chat.id, 'Ви підписалися на новини.')
    else:
        await bot.send_message(message.chat.id, 'Ви вже підписалися на новини.')


@dp.message_handler(commands=['stop'])
async def process_start_command(message: types.Message):
    if await unsubscribe_new(message.chat.id):
        await bot.send_message(message.chat.id, 'Ви відписалися від новин.')
    else:
        await bot.send_message(message.chat.id, 'Ви вже відписалися від новин.')


if __name__ == '__main__':
    while True:
        try:
            executor.start_polling(dp, skip_updates=False, on_startup=on_startup)
        except:
            time.sleep(15)
