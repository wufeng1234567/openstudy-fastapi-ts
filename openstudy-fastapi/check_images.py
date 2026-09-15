import asyncio
import aiomysql

async def check():
    conn = await aiomysql.connect(host='localhost', port=3306, user='root', password='123456', db='student_learning')
    cur = await conn.cursor()

    # Check question content for image references
    await cur.execute("""
        SELECT id, LEFT(question_text, 200), LEFT(content, 200)
        FROM question_main
        WHERE question_text LIKE '%<%' OR content LIKE '%<%'
           OR question_text LIKE '%http%' OR content LIKE '%http%'
        LIMIT 5
    """)
    rows = await cur.fetchall()
    print(f"Questions with HTML/URLs: {len(rows)}")
    for r in rows:
        print(f"\nID: {r[0]}")
        print(f"  text: {r[1]}")
        print(f"  content: {r[2]}")

    # Check uploads directory
    await cur.execute("SELECT cover_image FROM question_bank WHERE cover_image IS NOT NULL AND cover_image != '' LIMIT 3")
    covers = await cur.fetchall()
    print(f"\nCover images:")
    for c in covers:
        print(f"  {c[0]}")

    conn.close()

asyncio.run(check())
