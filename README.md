# Bot Ticket - Discord Romanesc

Bot de ticket pentru server Discord romanesc.

## Ce face

- Trimite automat mesajul de ticket in canalul configurat.
- Buton: `Creează Ticket`.
- Cand un user apasa butonul, botul ii cere ID-ul din joc.
- Creeaza un canal privat `ticket-suport-user`.
- Fiecare user poate avea doar 1 ticket deschis.
- Ticketul poate fi inchis doar de rolul autorizat.
- La inchidere, canalul se sterge automat.

## Variabile Railway

```env
DISCORD_TOKEN=token_bot_ticket
TICKET_PANEL_CHANNEL_ID=1516534368225591386
TICKET_SUPPORT_ROLE_ID=1505906083812737134
TICKET_CLOSE_ROLE_ID=1516627835538903140
TICKET_CATEGORY_ID=0
TICKET_CHANNEL_PREFIX=ticket-suport
TICKET_DELETE_DELAY=5
NIXPACKS_PYTHON_VERSION=3.11
```

## Roluri

- Rol care vede si scrie in ticketuri: `1505906083812737134`
- Rol care poate apasa butonul `Ticket terminat`: `1516627835538903140`

## Permisiuni bot

Recomandat: Administrator.

Sau minim:

- View Channels
- Send Messages
- Read Message History
- Manage Channels
- Manage Messages
- Use Slash Commands
- Attach Files
- Embed Links

## Developer Portal

Activeaza:

- Server Members Intent

## Comenzi

- `/ticket_setup`
- `/ticket_status`
