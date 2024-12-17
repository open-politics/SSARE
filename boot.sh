sudo mkdir -p ./opol/stack/.store/data/placeholder
sudo chmod 777 ./opol/stack/.store/data/placeholder

sudo sysctl vm.overcommit_memory=1

sudo docker compose -f ./opol/stack/compose.yml up --build # -d

# sleep 10

# sudo docker exec -it opol-ollama-1 ollama pull llama3.1