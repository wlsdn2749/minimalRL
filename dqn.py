import gymnasium as gym
import collections
import random
import glob 

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim

import os
import wandb 

#Hyperparameters
learning_rate = 0.0005
gamma         = 0.98
buffer_limit  = 50000
batch_size    = 32

class ReplayBuffer():
    def __init__(self):
        self.buffer = collections.deque(maxlen=buffer_limit)
        
    def __len__(self):
        return len(self.buffer)
     
    def put(self, transition):
        self.buffer.append(transition)
    
    def sample(self, n):
        mini_batch = random.sample(self.buffer, n)
        s_lst, a_lst, r_lst, s_prime_lst, done_mask_lst = [], [], [], [], []
        
        for transition in mini_batch:
            s, a, r, s_prime, done_mask = transition
            s_lst.append(s)
            a_lst.append([a])
            r_lst.append([r])
            s_prime_lst.append(s_prime)
            done_mask_lst.append([done_mask])

        return torch.tensor(s_lst, dtype=torch.float), torch.tensor(a_lst), \
               torch.tensor(r_lst), torch.tensor(s_prime_lst, dtype=torch.float), \
               torch.tensor(done_mask_lst)
    
    def size(self):
        return len(self.buffer)

class Qnet(nn.Module):
    def __init__(self):
        super(Qnet, self).__init__()
        self.fc1 = nn.Linear(4, 128)
        self.fc2 = nn.Linear(128, 128)
        self.fc3 = nn.Linear(128, 2)

    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = self.fc3(x)
        return x
      
    def sample_action(self, obs, epsilon):
        out = self.forward(obs)
        coin = random.random()
        if coin < epsilon:
            return random.randint(0,1)
        else: 
            return out.argmax().item()
            
def train(q, q_target, memory, optimizer):
    for i in range(10):
        s,a,r,s_prime,done_mask = memory.sample(batch_size)

        q_out = q(s)
        q_a = q_out.gather(1,a)
        max_q_prime = q_target(s_prime).max(1)[0].unsqueeze(1)
        target = r + gamma * max_q_prime * done_mask
        loss = F.smooth_l1_loss(q_a, target)
        
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

def main():
    run = wandb.init(
        project = f'minRL_lightning_{os.path.basename(__file__)}'
    )
    env = gym.make('CartPole-v1', render_mode='rgb_array')
    # env = gym.wrappers.RecordVideo(env, 
    #                                video_folder=f'./videos/{run.id}', 
    #                                episode_trigger= lambda x : x % 2000 == 0)
    q = Qnet()
    q_target = Qnet()
    q_target.load_state_dict(q.state_dict())
    memory = ReplayBuffer()

    print_interval = 20
    score = 0.0  
    steps = 0
    optimizer = optim.Adam(q.parameters(), lr=learning_rate)

    for n_epi in range(10000):
        epsilon = max(0.01, 0.08 - 0.01*(n_epi/200)) #Linear annealing from 8% to 1%
        s, _ = env.reset()
        done = False
        epi_per_step = 0
        while not done:
            a = q.sample_action(torch.from_numpy(s).float(), epsilon)      
            s_prime, r, done, truncated, info = env.step(a)
            # print(s_prime, r, done, truncated, info)
            steps += 1
            epi_per_step += 1
            print(epi_per_step, r, done, truncated)
            done_mask = 0.0 if done else 1.0
            memory.put((s,a,r/100.0,s_prime, done_mask))
            s = s_prime

            score += r
            env.render()
            
        print(n_epi)
            
        if memory.size() > 2000:
            train(q, q_target, memory, optimizer)

        if n_epi % print_interval==0 and n_epi!=0:
            q_target.load_state_dict(q.state_dict())
            print("n_episode :{}, score : {:.1f}, n_buffer : {}, eps : {:.1f}%".format(
                                                            n_epi, score/print_interval, memory.size(), epsilon*100))
            score = 0.0
                      
        wandb.log({"Reward": score,
                   "Steps": steps,
                   "Episode": n_epi,
                   "Buffer size": memory.__len__()})
            
        mp4list = glob.glob(f'./videos/{run.id}/*.mp4')
        if len(mp4list) > 1:
            mp4 = mp4list[-2]            
            wandb.log({"gameplays": wandb.Video(mp4, caption='episode: '+str(n_epi-2000), fps=4, format="gif"), "Episode": n_epi})
        
    env.close()

if __name__ == '__main__':
    main()
