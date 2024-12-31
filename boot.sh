sudo mkdir -p ./opol/stack/.store/data/placeholder
sudo chmod 777 ./opol/stack/.store/data/placeholder

cd opol/stack
mv .env.example .env
mv .env.local.example .env.local

sudo sysctl -w vm.overcommit_memory=1

sudo docker-compose -f compose.local.yml up --build -d

sleep 10

sudo docker exec -it opol-ollama-1 ollama pull llama3.1