# Scenarios: 93 everyday computer tasks

Each batch runs on one desktop prepared by `setup.py KIND` (KIND in brackets). Each line is the task as a user
would ask it, then how to check it afterwards. The scenario site logs what its pages report to
/tmp/gym-results.jsonl inside the desktop.
Site = http://localhost:8765/ (inside the desktop). Files: ~/Documents, ~/Pictures, ~/Downloads, ~/Videos.
Each scenario: ID · task as a user would ask it · check (run after, with `m check-ID`).

## Batch web1 [web]
- W01 · On localhost:8765/signup.html create an account: name "Maya Cohen", email maya.cohen@example.com, password "Tr0pical!Rain" (confirmed), phone +972 50 555 0101, plan Pro, interests Music and Travel, country Israel, born 1992-04-17, 7 years of experience, about you "Product designer who loves hiking.", accept the terms. · check: grep '"task": "signup"' /tmp/gym-results.jsonl
- W02 · Complete the 3-step checkout at localhost:8765/wizard.html for "Ido Katz", ido@example.com, 12 Herzl St, Haifa, ZIP 33031. Choose Express shipping and place the order. Tell me the order number. · check: grep wizard
- W03 · On localhost:8765/table.html, what is the total salary of everyone in the Engineering department, and how many people is that? · answer key
- W04 · On localhost:8765/infinite.html, what is the reference code of Entry 87? · answer key
- W05 · On localhost:8765/popups.html, get the "Alpine Escapes 2027" brochure (popups will get in the way). · check: grep '"task": "popups"'
- W06 · On localhost:8765/alerts.html, change the display name to "Captain Nemo", then sign out of all devices (confirm it). · check: grep alerts
- W07 · Pay invoice INV-2207 at localhost:8765/iframe.html with: name Dana Levi, card 4242 4242 4242 4242, expiry 08/29, CVC 123. Tell me the receipt number. · check: grep iframe
- W08 · On the sprint board at localhost:8765/kanban.html, move "Pay rent" to Done and "Book dentist" to In progress. · check: grep kanban (last line)
- W09 · On localhost:8765/hover.html, open the Billing settings from the account menu. · check: grep hover
- W10 · On localhost:8765/autocomplete.html, set the destination country to Israel and continue. · check: grep autocomplete
- W11 · Book a table at localhost:8765/datepicker.html for 15 March 2027, 4 guests. · check: grep datepicker
- W12 · On localhost:8765/slow.html, generate the report and tell me how many rows were processed and how many transactions were flagged. · answer 4,217 / 38
- W13 · On localhost:8765/toast.html, save a draft titled "Weekly update" with any body, and tell me the draft code the app shows. · check: grep toast (code)
- W14 · Real web: on https://the-internet.herokuapp.com/javascript_alerts click "Click for JS Prompt", answer "minion", and tell me the result text.
- W15 · Real web: what is the price of "Sapiens: A Brief History of Humankind" on https://books.toscrape.com/ ?

## Batch web2 [web]
- B01 · At localhost:8765/newtab.html sign in: the Terms of Use link opens in a new tab: enter its version number, and use Single Sign-On to pick the work account (dana@work.example), then finish sign-in. · check: grep newtab
- B02 · At localhost:8765/shadow.html turn on the Air conditioner and set its level to 22. · check: grep shadow
- B03 · On localhost:8765/canvas.html, which region sold the most units, and how many? · answer East 538
- B04 · On localhost:8765/long.html reserve a seat in session 40. · check: grep long
- B05 · At localhost:8765/settings.html: dark mode on, autoplay videos off, volume 70, language Deutsch, then save. · check: grep settings
- B06 · At localhost:8765/scrollbox.html approve claim 2047 only. · check: grep scrollbox
- B07 · At localhost:8765/editor.html publish a post titled "Release notes" whose body is a sentence with the word "faster" in bold, followed by a bulleted list of two items. · check: grep editor
- B08 · At localhost:8765/ambiguous.html empty the Spam folder (only Spam). · check: grep ambiguous
- B09 · At localhost:8765/upload.html upload ~/Documents/notes.txt and submit. · check: grep upload
- B10 · From localhost:8765/downloads.html download the September 2026 card expenses. What is the total amount, and how many empty rows does the file have? · answer key
- B11 · Register at localhost:8765/he.html (a Hebrew page): name "דנה לוי", phone 050-1234567, city Haifa (חיפה), agree to updates, and send. · check: grep '"task": "he"'
- B12 · Sign in to localhost:8765/login.html (customer ID dana42, password Harbor#2026). What is the checking account balance? · answer $2,318.77
- B13 · Real web: what population does English Wikipedia's infobox give for Iceland?
- B14 · Real web: on Japanese Wikipedia (ja.wikipedia.org), what population does the 東京都 (Tokyo) article's infobox give?
- B15 · Real web: on https://todomvc.com/examples/react/dist/ add three todos (milk, bread, eggs), complete "bread", filter Active, and tell me how many items are left.

## Batch office [office]
- O01 · Create ~/Documents/budget.xlsx: columns Item and Amount, 5 expenses (Rent 4200, Food 1800, Transport 450, Phone 120, Gym 199), a Total row with a SUM formula, header in bold. · check: read budget.xlsx
- O02 · Sort ~/Documents/sales.csv by Revenue (highest first) and save it as ~/Documents/sales_sorted.xlsx. · check: read
- O03 · Make a bar chart of total Revenue per Region from ~/Documents/sales.csv and save the workbook as ~/Documents/sales_chart.xlsx (chart inside). · check: unzip -l | grep chart
- O04 · Write a short letter in Writer: a "Heading 1" title "Welcome to the team", two paragraphs, a bulleted list of three first-week tasks. Save as ~/Documents/letter.docx and also export ~/Documents/letter.pdf. · check: read both
- O05 · In ~/Documents/report.docx replace every "ACME" with "Globex" and save it (same file, docx). · check: read | grep -c
- O06 · Create a 3-slide presentation ~/Documents/pitch.pptx: a title slide "Nimbus" + subtitle, then two slides with a title and three bullets each. · check: read pitch.pptx
- O07 · New Writer document with the image ~/Pictures/logo.png centered at the top and the line "Quarterly newsletter" under it; save as ~/Documents/newsletter.docx. · check: unzip -l | grep media
- O08 · Open ~/Documents/sales.csv in Calc, freeze the header row, make Revenue cells above 100000 have a red background (conditional formatting), save as ~/Documents/sales_formatted.xlsx. · check: unzip -p xl/worksheets/sheet1.xml | grep -o 'pane\|conditionalFormatting'
- O09 · Merge ~/Documents/chapter1.pdf and chapter2.pdf (in that order) into ~/Documents/book.pdf. · check: pdfinfo pages=4
- O10 · In ~/Documents/report.docx turn on Track Changes, change "14%" to "15%" and add a comment "Check with finance" on that paragraph; save. · check: unzip -p word/document.xml | grep -c 'w:ins\|w:del'; comments.xml
- O11 · For each person in ~/Documents/people.csv make a PDF letter ~/Documents/letters/<first_name>.pdf saying "Dear <first name>, your balance is <amount_due> ILS." · check: ls; read one
- O12 · Put the line items of the table in ~/Documents/invoice.pdf into ~/Documents/invoice.xlsx (Item, Qty, Unit price, Line total) with a total row. · check: read
- O13 · Make ~/Documents/report.docx landscape with 2 cm margins on all sides and save. · check: unzip -p word/document.xml | grep -o 'w:orient="landscape"\|w:pgMar[^>]*'
- O14 · Insert a table of contents at the top of ~/Documents/report.docx (after the title) and save. · check: grep -c TOC
- O15 · In ~/Documents/sales.csv add a column "VAT" = Revenue × 0.17 for every row (as formulas), save as ~/Documents/sales_vat.xlsx. · check: read (formulas)

## Batch everyday [everyday]
- E01 · What's the date and time on this computer, and how much free disk space is there?
- E02 · Open example.com and tell me the page's heading.
- E03 · Using the Text Editor app (not the shell), write a shopping list (milk, eggs, bread, one per line) and save it as ~/Documents/shopping.txt. · check: cat
- E04 · Use a calculator app (install one if needed) to compute 1234 × 5678 ÷ 3. Tell me the result as shown by the app.
- E05 · Copy the first paragraph of the English Wikipedia article on Alan Turing into ~/Documents/turing.txt. · check: cat
- E06 · Using the file manager (Files app), rename the three .jpeg files in ~/Pictures to .jpg. · check: ls
- E07 · Find the biggest file in ~/Downloads and delete it. · check: ls
- E08 · Zip ~/Documents/project into ~/Documents/project.zip. · check: unzip -l
- E09 · In Firefox, open en.wikipedia.org, zoom the page to 150%, and confirm the zoom level Firefox shows.
- E10 · Search the web (DuckDuckGo) for "Minion featherweight desktops for AI agents" and tell me the first three result titles.
- E11 · Bookmark https://www.python.org/ in Firefox and confirm it's in the bookmarks.
- E12 · Open wikipedia.org and python.org in two tabs, then close the first tab. Which tab remains?
- E13 · In the Text Editor, type exactly: שלום עולם 👋 café naïve – 東京 and save it as ~/Documents/unicode.txt. · check: cat
- E14 · Open Writer, type "draft text", then close Writer without saving. Make sure no file was saved and Writer is closed.
- E15 · Open ~/Documents/notes.txt in the Text Editor, then open Firefox and the Files app on top of it. Go back to the Text Editor, add the line "- call the bank" at the end and save. · check: cat
- E16 · What's the Wi-Fi access code on the sign in ~/Pictures/wifi-sign.png?
- E17 · What's in the picture ~/Pictures/receipt.jpg: the store, and the total?

## Batch workflows [workflows]
- C01 · In the webmail at localhost:8765/mail.html, find Dana Peretz's email with the final Q3 figures, total the "amount" column of its attachment, and reply to Dana with the total. · check: grep mail-send
- C02 · At localhost:8765/shop.html buy 3 of the cheapest USB flash drive and 1 "USB-C cable 2 m", Express shipping, promo code SAVE10, name Dana Levi, address 5 Herzl St, Haifa. What was the total charged? · check: grep shop
- C03 · Add every person in ~/Documents/people.csv as a contact at localhost:8765/contacts.html (first, last, email, city, amount due). · check: grep -c contacts = 5
- C04 · Make ~/Documents/population.xlsx with the 5 most populous countries (from Wikipedia) and their population, plus a bar chart. · check: read; chart
- C05 · Put a screenshot of https://www.python.org/ into a Writer document with the caption "Python home page" under it and save it as ~/Documents/python.pdf. · check: pdfimages -list
- C06 · ~/Pictures/receipt.jpg is a photo of a receipt. Make ~/Documents/receipt.xlsx with each item and its price and a total formula. · check: read
- C07 · Find the year each of Python, Rust and Go first appeared (Wikipedia) and save a two-column table (Language, Year) in ~/Documents/languages.docx. · check: read

## Batch dev [dev]
- D01 · The tests in ~/proj fail. Find out why and fix the code (not the tests). · check: cd ~/proj && python3 -m pytest -q
- D02 · In a terminal window (the GUI terminal, not `run`), start python3, compute 2**100 and exit. Tell me the number.
- D03 · Using the Geany editor (GUI), change the port in ~/config.ini from 8080 to 9090 and save. · check: cat
- D04 · Serve ~/site2 on port 8000 and confirm in Firefox that the page says "Hello from site2".
- D05 · Using vim in the GUI terminal, append the line "- ship v2 on Friday" to ~/notes.txt and save. · check: cat
- D06 · Something is eating memory. Find the process using the most memory and stop it if it's a script of ours. · check: pgrep -f hog.py
- D07 · Install cowsay and make the cow say "hello minion". Show me the output.
- D08 · Make ~/proj a git repository, commit everything on a branch called "fix", and show me the log. · check: git -C ~/proj log --oneline --all
- D09 · Open htop in the GUI terminal and tell me which process uses the most CPU (as htop shows it).
- D10 · Use Chromium (not Firefox) to sign up at http://localhost:8765/contacts.html: add yourself as first name "Test", email test@example.com. · check: grep contacts

## Batch media [media]
- M01 · Make a copy of ~/Pictures/photo.png at half the size, ~/Pictures/photo_small.png. · check: file
- M02 · Open ~/Pictures/photo.png in GIMP, make it grayscale and export it as ~/Pictures/photo_gray.jpg. · check: file/identify
- M03 · How long is ~/Videos/clip.mp4, and what's its resolution?
- M04 · Make an animated GIF ~/Pictures/slideshow.gif from the three vacation images (1 second each). · check: file
- M05 · In a paint program, draw a red filled rectangle on a white canvas and save it as ~/Pictures/rect.png. · check: python3 PIL red pixels
- M06 · In GIMP, crop ~/Pictures/photo.png to its centre 800x500 region (offset 400,250) and export it as ~/Pictures/photo_crop.png. · check: python3 -c "from PIL import Image; print(Image.open('photo_crop.png').size)"
- M07 · Grab the frame at 3 seconds from ~/Videos/clip.mp4 as ~/Pictures/frame_3s.png and tell me what it shows.

## Batch windows [windows]
- X01 · In Windows Notepad, write "Meeting at 10:00 with Dana" and save it as Documents\note.txt in the Windows user's folder. · check: find ~/.wine -name note.txt
- X02 · In the Windows Command Prompt, what does `ver` print?
- X03 · In the Windows Registry Editor, create the key HKEY_CURRENT_USER\Software\MinionTest with a string value Color = Blue. · check: wine reg query
- X04 · In Wine's settings (winecfg), set the Windows version to Windows 10 and apply. · check: wine reg query HKLM ... CurrentVersion
- X05 · Open notes.txt from the Windows user's Documents folder in Notepad, add a line "- renew passport" at the end, and save it. · check: cat ~/Documents/notes.txt
- X06 · Using Windows Explorer, create a folder named "Projects 2027" in the Windows user's Documents folder. · check: ls -d ~/Documents/"Projects 2027"
- X07 · Using the Windows Command Prompt, list my Windows Documents folder and tell me what's in it (names and sizes) and how much free space `dir` reports.
