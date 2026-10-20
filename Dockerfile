FROM mcr.microsoft.com/playwright:v1.40.0-focal

WORKDIR /usr/src/app

# Copia arquivos do projeto e instala pacotes
COPY package*.json ./
RUN npm install

# Copia o restante do código
COPY . .

EXPOSE 5000

CMD ["node", "server.js"]
