from .rl_agent import RLAgent
from common.registry import Registry
import random
import numpy as np
from collections import deque, OrderedDict
import os
import pickle
import time
import torch
from torch import nn
import torch.nn.functional as F
import torch.optim as optim
from torch.nn.utils import clip_grad_norm_
from torch_geometric.nn import MessagePassing
from torch_geometric.utils import add_self_loops
from torch_geometric.data import Data, Batch
import torch_scatter


class Embedding_MLP(nn.Module):
    def __init__(self, in_size, layers):
        super(Embedding_MLP, self).__init__()
        constructor_dict = OrderedDict()
        for l_idx, l_size in enumerate(layers):
            name = f"node_embedding_{l_idx}"
            if l_idx == 0:
                h = nn.Linear(in_size, l_size)
                constructor_dict.update({name: h})
            else:
                h = nn.Linear(layers[l_idx - 1], l_size)
                constructor_dict.update({name: h})
            name = f"n_relu_{l_idx}"
            constructor_dict.update({name: nn.ReLU()})

        self.embedding_node = nn.Sequential(constructor_dict)

    def _forward(self, x):
        x = self.embedding_node(x)
        return x

    def forward(self, x, train=True):
        if train:
            return self._forward(x)
        else:
            with torch.no_grad():
                return self._forward(x)

class MultiHeadAttModel(MessagePassing):
    """
    inputs:
        In_agent [bacth,agents,128]
        In_neighbor [agents, neighbor_num]
        l: number of neighborhoods (in my code, l=num_neighbor+1,because l include itself)
        d: dimension of agents's embedding
        dv: dimension of each head
        dout: dimension of output
        nv: number of head (multi-head attention)
    output:
        -hidden state: [batch,agents,32]
        -attention: [batch,agents,neighbor]
    """
    def __init__(self, d=128, dv=16, d_out=128, nv=8, suffix=-1):
        super(MultiHeadAttModel, self).__init__(aggr='add')
        self.d = d
        self.dv = dv
        self.d_out = d_out
        self.nv = nv
        self.suffix = suffix
        # target is center
        self.W_target = nn.Linear(d, dv * nv)
        self.W_source = nn.Linear(d, dv * nv)
        self.hidden_embedding = nn.Linear(d, dv * nv)
        self.out = nn.Linear(dv, d_out)
        self.att_list = []
        self.att = None

    def _forward(self, x, edge_index):
        # TODO: test batch is shared or not
        
        # 重要：清空att_list以防止显存泄漏
        self.att_list = []

        # x has shape [N, d], edge_index has shape [E, 2]
        edge_index, _ = add_self_loops(edge_index=edge_index)
        aggregated = self.propagate(x=x, edge_index=edge_index)  # [16, 16]
        out = self.out(aggregated)
        out = F.relu(out)  # [ 16, 128]
        #self.att = torch.tensor(self.att_list)
        return out

    def forward(self, x, edge_index, train=True):
        if train:
            return self._forward(x, edge_index)
        else:
            with torch.no_grad():
                return self._forward(x, edge_index)

    def message(self, x_i, x_j, edge_index):
        h_target = F.relu(self.W_target(x_i))
        h_target = h_target.view(h_target.shape[:-1][0], self.nv, self.dv)
        agent_repr = h_target.permute(1, 0, 2)

        h_source = F.relu(self.W_source(x_j))
        h_source = h_source.view(h_source.shape[:-1][0], self.nv, self.dv)
        neighbor_repr = h_source.permute(1, 0, 2)   #[nv, E, dv]
        index = edge_index[1]  # which is target
        #TODO: confirm its a vector of size E
        # method 1: e_i = torch.einsum()
        # method 2: e_i = torch.bmm()
        # method 3: e_i = (a * b).sum(-1)
        e_i = torch.mul(agent_repr, neighbor_repr).sum(-1)  # [5, 64]
        max_node = torch_scatter.scatter_max(e_i, index=index)[0]  # [5, 16]
        max_i = max_node.index_select(1, index=index)  # [5, 64]
        ec_i = torch.add(e_i, -max_i)
        ecexp_i = torch.exp(ec_i)
        norm_node = torch_scatter.scatter_sum(ecexp_i, index=index)  # [5, 16]
        normst_node = torch.add(norm_node, 1e-12)  # [5, 16]
        normst_i = normst_node.index_select(1, index)  # [5, 64]

        alpha_i = ecexp_i / normst_i  # [5, 64]
        alpha_i_expand = alpha_i.repeat(self.dv, 1, 1)
        alpha_i_expand = torch.permute(alpha_i_expand, (1, 2, 0))  # [5, 64, 16]
        # TODO: test x_j or x_i here -> should be x_j
        hidden_neighbor = F.relu(self.hidden_embedding(x_j))
        hidden_neighbor = hidden_neighbor.view(hidden_neighbor.shape[:-1][0], self.nv, self.dv)
        hidden_neighbor_repr = hidden_neighbor.permute(1, 0, 2)  # [5, 64, 16]
        out = torch.mul(hidden_neighbor_repr, alpha_i_expand).mean(0)

        # 注意：使用detach()断开计算图，防止显存泄漏
        # 如果不需要attention信息，可以注释掉这行
        # self.att_list.append(alpha_i.detach())  # [64, 16]
        return out
    """
    def aggregate(self, inputs, edge_index):
        out = inputs
        index = edge_index[1]
    """




    def get_att(self):
        if self.att is None:
            print('invalid att')
        return self.att


class ColightNet(nn.Module):
    def __init__(self, input_dim, **kwargs):
        super(ColightNet, self).__init__()
        self.constructor_dict = kwargs
        self.action_space = self.constructor_dict.get('action_space') or 8
        self.modulelist = nn.ModuleList()
        self.embedding_MLP = Embedding_MLP(input_dim, layers=self.constructor_dict.get('NODE_EMB_DIM') or [128, 128])
        for i in range(self.constructor_dict.get('N_LAYERS')):
            module = MultiHeadAttModel(d=self.constructor_dict.get('INPUT_DIM')[i],
                                       dv=self.constructor_dict.get('NODE_LAYER_DIMS_EACH_HEAD')[i],
                                       d_out=self.constructor_dict.get('OUTPUT_DIM')[i],
                                       nv=self.constructor_dict.get('NUM_HEADS')[i],
                                       suffix=i)
            self.modulelist.append(module)
        output_dict = OrderedDict()

        """
        if self.constructor_dict.get('N_LAYERS') == 0:
            out = nn.Linear(128, self.action_space.n)
            name = f'output'
            output_dict.update({name: out})
            self.output_layer = nn.Sequential(output_dict)
        """
        output_dict = OrderedDict()
        if len(self.constructor_dict['OUTPUT_LAYERS']) != 0:
            # TODO: dubug this branch
            for l_idx, l_size in enumerate(self.constructor_dict['OUTPUT_LAYERS']):
                name = f'output_{l_idx}'
                if l_idx == 0:
                    h = nn.Linear(module.d_out, l_size)
                else:
                    h = nn.Linear(self.output_dict.get('OUTPUT_LAYERS')[l_idx - 1], l_size)
                output_dict.update({name: h})
                name = f'relu_{l_idx}'
                output_dict.update({name: nn.ReLU})
            out = nn.Linear(self.constructor_dict['OUTPUT_LAYERS'][-1], self.action_space.n)
        else:
            out = nn.Linear(module.d_out, self.action_space.n)
        name = f'output'
        output_dict.update({name: out})
        self.output_layer = nn.Sequential(output_dict)

    def forward(self, x, edge_index, train=True):
        h = self.embedding_MLP.forward(x, train)
        #TODO: implement att
        for mdl in self.modulelist:
            h = mdl.forward(h, edge_index, train)
        if train:
            h = self.output_layer(h)
        else:
            with torch.no_grad():
                h = self.output_layer(h)
        return h


@Registry.register_model('colight_pytorch_agent')
class CoLightAgent(RLAgent):
    def __init__(self, world, rank):
        super().__init__(world, world.intersection_ids[rank])
        
        # 从Registry获取配置
        self.buffer_size = Registry.mapping['trainer_mapping']['setting'].param['buffer_size']
        self.replay_buffer = deque(maxlen=self.buffer_size)
        
        self.graph = Registry.mapping['world_mapping']['graph_setting'].graph
        self.world = world
        self.sub_agents = len(self.world.intersections)
        
        # GPU设置
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"使用设备: {self.device}")
        
        # 图结构
        self.edge_idx = torch.tensor(self.graph['sparse_adj'].T, dtype=torch.long).to(self.device)
        
        # 模型参数
        self.phase = Registry.mapping['model_mapping']['setting'].param['phase']
        self.one_hot = Registry.mapping['model_mapping']['setting'].param['one_hot']
        self.model_dict = Registry.mapping['model_mapping']['setting'].param
        
        # 获取observation generators
        from generator import LaneVehicleGenerator, IntersectionPhaseGenerator
        observation_generators = []
        for inter in self.world.intersections:
            node_id = inter.id if 'GS_' not in inter.id else inter.id[3:]
            node_idx = self.graph['node_id2idx'][node_id]
            tmp_generator = LaneVehicleGenerator(self.world, inter, ['lane_count'], in_only=True, average=None)
            observation_generators.append((node_idx, tmp_generator))
        sorted(observation_generators, key=lambda x: x[0])
        self.ob_generator = observation_generators
        self.ob_length = max(gen[1].ob_length for gen in observation_generators)
        
        # 获取reward generators
        rewarding_generators = []
        for inter in self.world.intersections:
            node_id = inter.id if 'GS_' not in inter.id else inter.id[3:]
            node_idx = self.graph['node_id2idx'][node_id]
            tmp_generator = LaneVehicleGenerator(self.world, inter, ["lane_waiting_count"],
                                                 in_only=True, average='all', negative=True)
            rewarding_generators.append((node_idx, tmp_generator))
        sorted(rewarding_generators, key=lambda x: x[0])
        self.reward_generator = rewarding_generators
        
        # 获取queue generators
        queues = []
        for inter in self.world.intersections:
            node_id = inter.id if 'GS_' not in inter.id else inter.id[3:]
            node_idx = self.graph['node_id2idx'][node_id]
            tmp_generator = LaneVehicleGenerator(self.world, inter, ["lane_waiting_count"], 
                                                 in_only=True, negative=False)
            queues.append((node_idx, tmp_generator))
        sorted(queues, key=lambda x: x[0])
        self.queue = queues
        
        # 获取delay generators  
        delays = []
        for inter in self.world.intersections:
            node_id = inter.id if 'GS_' not in inter.id else inter.id[3:]
            node_idx = self.graph['node_id2idx'][node_id]
            tmp_generator = LaneVehicleGenerator(self.world, inter, ["lane_delay"], 
                                                 in_only=True, average="all", negative=False)
            delays.append((node_idx, tmp_generator))
        sorted(delays, key=lambda x: x[0])
        self.delay = delays
        
        # phase generators
        phasing_generators = []
        for inter in self.world.intersections:
            node_id = inter.id if 'GS_' not in inter.id else inter.id[3:]
            node_idx = self.graph['node_id2idx'][node_id]
            tmp_generator = IntersectionPhaseGenerator(self.world, inter, ['phase'],
                                                       targets=['cur_phase'], negative=False)
            phasing_generators.append((node_idx, tmp_generator))
        sorted(phasing_generators, key=lambda x: x[0])
        self.phase_generator = phasing_generators
        
        # agent rank (用于保存模型)
        self.rank = rank
        
        # DQN参数
        self.num_agents = self.sub_agents
        # 用所有路口相位数的最大值作为网络输出维度，
        # 确保相位数较多的路口的所有相位都能被选到。
        # get_action 中已用 action_vec[0:phase_length] 屏蔽各路口无效相位。
        self.phase_lengths = np.array([len(i.phases) for i in self.world.intersections])
        self.num_actions = int(self.phase_lengths.max())
        self.batch_size = self.model_dict.get('batch_size', 32)
        self.learning_rate = self.model_dict.get('learning_rate', 0.001)
        self.learning_start = self.model_dict.get('learning_start', 2000)
        self.update_model_freq = self.model_dict.get('update_model_freq', 1)
        self.update_target_model_freq = self.model_dict.get('update_target_model_freq', 20)
        self.gamma = self.model_dict.get('gamma', 0.95)
        self.epsilon = self.model_dict.get('epsilon', 0.8)
        self.epsilon_min = self.model_dict.get('epsilon_min', 0.01)
        self.epsilon_decay = self.model_dict.get('epsilon_decay', 0.995)
        self.grad_clip = self.model_dict.get('grad_clip', 5.0)
        self.vehicle_max = self.model_dict.get('vehicle_max', 1)
        
        self.world.subscribe("pressure")
        self.world.subscribe("lane_count")
        self.world.subscribe("lane_waiting_count")
        
        # 其他设置
        self.get_attention = self.model_dict.get('get_attention', False)
        
        # 构建图设置
        self.graph_setting = {
            'NODE_EMB_DIM': self.model_dict.get('NODE_EMB_DIM', [128]),
            'INPUT_DIM': self.model_dict.get('INPUT_DIM', [128]),
            'OUTPUT_DIM': self.model_dict.get('OUTPUT_DIM', [128]),
            'NODE_LAYER_DIMS_EACH_HEAD': self.model_dict.get('NODE_LAYER_DIMS_EACH_HEAD', [16]),
            'NUM_HEADS': self.model_dict.get('NUM_HEADS', [8]),
            'N_LAYERS': self.model_dict.get('N_LAYERS', 1),
            'OUTPUT_LAYERS': self.model_dict.get('OUTPUT_LAYERS', []),
            'action_space': type('obj', (object,), {'n': self.num_actions})()
        }
        self.passer = self.graph_setting  # 传递给模型构建
        self.action_space = self.graph_setting['action_space']  # 为了兼容性
        
        # 构建模型
        self.criterion = nn.MSELoss(reduction='mean')
        self.model = self._build_model().to(self.device)
        self.target_model = self._build_model().to(self.device)
        self.update_target_network()
        self.optimizer = optim.RMSprop(self.model.parameters(), lr=self.learning_rate, alpha=0.9, centered=False, eps=1e-7)
        #for i in self.model.named_parameters():
        #    print(i)

    def _build_model(self):
        """
        layer definition
        """
        """
        #[#agents,batch,feature_dim],[#agents,batch,neighbors,agents],[batch,1,neighbors]
        ->[#agentsxbatch,feature_dim],[#agentsxbatch,neighbors,agents],[batch,1,neighbors]
        """
        # In: [batch,agents,feature]
        # In: [batch,agents,neighbors,agents]
        # In.append(Input(shape=[self.num_agents,self.len_feature],name="feature"))
        # In.append(Input(shape=(self.num_agents,self.num_neighbors,self.num_agents),name="adjacency_matrix"))
        #TODO: keep no phase
        model = ColightNet(self.ob_length, **self.passer)
        #model = ColightNet(self.action_space.n + self.ob_length, **self.passer)
        # if self.graph_setting["N_LAYERS"]>1:
        #     att_record_all_layers=Concatenate(axis=1)(att_record_all_layers)
        # else:
        #     att_record_all_layers=att_record_all_layers[0]

        # att_record_all_layers=Reshape((self.graph_setting["N_LAYERS"],self.num_agents,self.graph_setting["NUM_HEADS"][self.graph_setting["N_LAYERS"]-1],self.graph_setting["NEIGHBOR_NUM"]+1))(att_record_all_layers)

        # out = Dense(self.action_space.n,kernel_initializer='random_normal',name='action_layer')(h)
        # out:[batch,agents,action], att:[batch,layers,agents,head,neighbors]
        # model=Model(inputs=In,outputs=[out,att_record_all_layers])
        print(model)
        return model

    def get_action(self, ob, phase, test=False):
        """
        与colight.py保持一致的参数顺序和命名
        :param ob: [agents, ob_length] observation
        :param phase: [agents] phase
        :param test: boolean, exploit while training and determined while testing
        :return: [batch,agents] action taken by environment
        """
        if not test:
            # print("train_phase")
            if np.random.rand() <= self.epsilon:
                return self.sample()
        # ob = self._reshape_ob(ob)
        # act_values = self.model.predict([phase, ob])

        e_ob = torch.tensor(ob, dtype=torch.float32).to(self.device)
        edge = self.edge_idx
        dt = Data(x=e_ob, edge_index=edge)

        #e_phase = F.one_hot(torch.tensor(phase, dtype=torch.long), self.action_space.n)
        #x = torch.concat([e_ob, e_phase], dim=1)
        #data = Data(x=x, edge_index=self.graph_setting['edge_idx'])

        # observations = np.concatenate([phase,ob],axis=-1)
        # observations = observations[np.newaxis,:]
        if self.get_attention:
            # TODO: no phase here
            actions = self.model.forward(x=dt.x, edge_index=dt.edge_index)
            att = self.get_attention
            #TODO: implement att
            actions = actions.detach().cpu().numpy()
            # 处理不同路口不同相位数量的情况
            action_list = []
            for action_vec, phase_length in zip(actions, self.phase_lengths):
                action_list.append(np.argmax(action_vec[0:phase_length]))
            action = np.array(action_list)
            return action, att  # [batch, agents],[batch,agents,nv,neighbor]
        else:
            actions = self.model.forward(x=dt.x, edge_index=dt.edge_index)
            actions = actions.detach().cpu().numpy()
            # 处理不同路口不同相位数量的情况
            action_list = []
            for action_vec, phase_length in zip(actions, self.phase_lengths):
                action_list.append(np.argmax(action_vec[0:phase_length]))
            action = np.array(action_list)
            return action  # batch, agents

    def sample(self):
        # 与colight.py保持一致，不需要参数
        action = np.random.randint(0, self.action_space.n, self.sub_agents)
        action = np.clip(action, 0, self.phase_lengths - 1)
        return action

    def get_reward(self):
        """
        获取奖励 - 使用reward_generator直接生成
        与colight.py保持一致的简单实现
        """
        rewards = []  # sub_agents
        for i in range(len(self.reward_generator)):
            rewards.append(self.reward_generator[i][1].generate())
        rewards = np.squeeze(np.array(rewards, dtype=np.float32)) * 12
        return rewards

    def reset(self):
        """
        Reset all generators (called at the start of each episode)
        """
        from generator import LaneVehicleGenerator, IntersectionPhaseGenerator
        
        # Reset observation generators
        observation_generators = []
        for inter in self.world.intersections:
            node_id = inter.id if 'GS_' not in inter.id else inter.id[3:]
            node_idx = self.graph['node_id2idx'][node_id]
            tmp_generator = LaneVehicleGenerator(self.world, inter, ['lane_count'], in_only=True, average=None)
            observation_generators.append((node_idx, tmp_generator))
        sorted(observation_generators, key=lambda x: x[0])
        self.ob_generator = observation_generators
        
        # Reset reward generators
        rewarding_generators = []
        for inter in self.world.intersections:
            node_id = inter.id if 'GS_' not in inter.id else inter.id[3:]
            node_idx = self.graph['node_id2idx'][node_id]
            tmp_generator = LaneVehicleGenerator(self.world, inter, ["lane_waiting_count"],
                                                 in_only=True, average='all', negative=True)
            rewarding_generators.append((node_idx, tmp_generator))
        sorted(rewarding_generators, key=lambda x: x[0])
        self.reward_generator = rewarding_generators
        
        # Reset phase generators
        phasing_generators = []
        for inter in self.world.intersections:
            node_id = inter.id if 'GS_' not in inter.id else inter.id[3:]
            node_idx = self.graph['node_id2idx'][node_id]
            tmp_generator = IntersectionPhaseGenerator(self.world, inter, ['phase'],
                                                       targets=['cur_phase'], negative=False)
            phasing_generators.append((node_idx, tmp_generator))
        sorted(phasing_generators, key=lambda x: x[0])
        self.phase_generator = phasing_generators
        
        # Reset queue generators
        queues = []
        for inter in self.world.intersections:
            node_id = inter.id if 'GS_' not in inter.id else inter.id[3:]
            node_idx = self.graph['node_id2idx'][node_id]
            tmp_generator = LaneVehicleGenerator(self.world, inter, ["lane_waiting_count"], 
                                                 in_only=True, negative=False)
            queues.append((node_idx, tmp_generator))
        sorted(queues, key=lambda x: x[0])
        self.queue = queues
        
        # Reset delay generators
        delays = []
        for inter in self.world.intersections:
            node_id = inter.id if 'GS_' not in inter.id else inter.id[3:]
            node_idx = self.graph['node_id2idx'][node_id]
            tmp_generator = LaneVehicleGenerator(self.world, inter, ["lane_delay"], 
                                                 in_only=True, average="all", negative=False)
            delays.append((node_idx, tmp_generator))
        sorted(delays, key=lambda x: x[0])
        self.delay = delays
    
    def get_ob(self):
        """
        return: obersavtion of node, observation of edge
        """
        x_obs = []  # num_agents * lane_nums,
        for i in range(len(self.ob_generator)):
            item = (self.ob_generator[i][1].generate()) / self.vehicle_max
            # 填充到统一长度以处理不同交叉口车道数不同的情况
            item = np.pad(item, (0, self.ob_length - item.shape[-1]))
            x_obs.append(item)
        # construct edge infomation
        x_obs = np.array(x_obs)
        return x_obs
    
    def get_phase(self):
        """
        get phase of intersection
        """
        phase = []
        for i in range(len(self.phase_generator)):
            phase.append((self.phase_generator[i][1].generate()))
        phase = (np.concatenate(phase)).astype(np.int8)
        return phase
    
    def get_queue(self):
        """
        get queue length of intersection
        """
        queue = []
        for item in self.queue:
            item = item[1].generate()
            item = np.pad(item, (0, self.ob_length - item.shape[-1]))
            queue.append(item)
        tmp_queue = np.squeeze(np.array(queue, dtype=np.float32))
        queue = np.sum(tmp_queue, axis=1 if len(tmp_queue.shape)==2 else 0)
        return queue
    
    def get_delay(self):
        """
        get delay of intersection
        """
        delay = []
        for i in range(len(self.delay)):
            delay.append((self.delay[i][1].generate()))
        delay = np.squeeze(np.array(delay, dtype=np.float32))
        return delay

    def remember(self, last_obs, last_phase, actions, actions_prob, rewards, obs, cur_phase, done, key):
        """
        存储经验到replay buffer
        与colight.py保持一致的签名
        """
        self.replay_buffer.append((key, (last_obs, last_phase, actions, rewards, obs, cur_phase)))
    """
    def _encode_sample(self, minibatch):
        batch_list = []
        batch_list_p = []
        #ob_t, phase_t, actions_t, rewards_t, ob_tp1, phase_tp1 = list(zip(*minibatch))
        #rewards = torch.tensor(rewards_t, dtype=torch.float32)
        #actions = actions_t
        actions = []
        rewards = []
        for dp in minibatch:
            cat = F.one_hot(torch.tensor(dp[1], dtype=torch.long).to(self.device), self.action_space.n)
            state = torch.tensor(dp[0], dtype=torch.float32).to(self.device)
            x = torch.concat([state, cat], dim=1)
            batch_list.append(Data(x=x, edge_index=self.edge_idx))
            cat_p = F.one_hot(torch.tensor(dp[5], dtype=torch.long).to(self.device), self.action_space.n)
            state_p = torch.tensor(dp[4], dtype=torch.float32).to(self.device)
            x_p = torch.concat([state_p, cat_p], dim=1)
            batch_list_p.append(Data(x=x_p, edge_index=self.edge_idx))
            rewards.append(dp[3])
            actions.append(dp[2])
        batch_t = Batch.from_data_list(batch_list)
        batch_tp = Batch.from_data_list(batch_list_p)
        # TODO reshape slow warning
        rewards = torch.tensor(np.array(rewards), dtype=torch.float32).to(self.device)
        rewards = rewards.view(rewards.shape[0] * rewards.shape[1])
        actions = torch.tensor(np.array(actions), dtype=torch.long).to(self.device)
        actions = actions.view(actions.shape[0] * actions.shape[1])
        return batch_t, batch_tp, rewards, actions
    """

    def _batchwise(self, samples):
        """
        将样本批量转换为tensor
        与colight.py保持一致，但增加GPU支持
        """
        batch_list = []
        batch_list_p = []
        actions = []
        rewards = []
        for item in samples:
            dp = item[1]  # 提取数据部分（跳过key）
            state = torch.tensor(dp[0], dtype=torch.float32).to(self.device)
            batch_list.append(Data(x=state, edge_index=self.edge_idx))

            state_p = torch.tensor(dp[4], dtype=torch.float32).to(self.device)
            batch_list_p.append(Data(x=state_p, edge_index=self.edge_idx))
            rewards.append(dp[3])
            actions.append(dp[2])
        batch_t = Batch.from_data_list(batch_list)
        batch_tp = Batch.from_data_list(batch_list_p)
        
        # 转换为tensor
        rewards = torch.tensor(np.array(rewards), dtype=torch.float32).to(self.device)
        actions = torch.tensor(np.array(actions), dtype=torch.long).to(self.device)
        
        # 如果有多个agent，需要reshape
        if self.sub_agents > 1:
            rewards = rewards.view(rewards.shape[0] * rewards.shape[1])
            actions = actions.view(actions.shape[0] * actions.shape[1])
        
        return batch_t, batch_tp, rewards, actions

    def train(self):
        """
        训练模型 - 与colight.py保持一致
        """
        # 显存监控（可选，调试时开启）
        debug_memory = False
        if debug_memory and torch.cuda.is_available():
            allocated_before = torch.cuda.memory_allocated(self.device) / 1024**2
            
        samples = random.sample(self.replay_buffer, self.batch_size)
        b_t, b_tp, rewards, actions = self._batchwise(samples)
        
        out = self.target_model(x=b_tp.x, edge_index=b_tp.edge_index, train=False)
        target = rewards + self.gamma * torch.max(out, dim=1)[0]
        target_f = self.model(x=b_t.x, edge_index=b_t.edge_index, train=False)

        for i, action in enumerate(actions):
            target_f[i][action] = target[i]
        loss = self.criterion(self.model(x=b_t.x, edge_index=b_t.edge_index, train=True), target_f)
        self.optimizer.zero_grad()
        loss.backward()
        clip_grad_norm_(self.model.parameters(), self.grad_clip)
        self.optimizer.step()
        
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay
        
        # 显存监控输出
        if debug_memory and torch.cuda.is_available():
            allocated_after = torch.cuda.memory_allocated(self.device) / 1024**2
            print(f"[Memory] Before: {allocated_before:.1f}MB, After: {allocated_after:.1f}MB, "
                  f"Diff: {allocated_after - allocated_before:.1f}MB")
        
        return loss.clone().detach().cpu().numpy()

    def update_target_network(self):
        """
        更新目标网络
        """
        weights = self.model.state_dict()
        self.target_model.load_state_dict(weights)

    def load_model(self, e):
        """
        加载模型 - 与colight.py保持一致
        """
        model_name = os.path.join(Registry.mapping['logger_mapping']['path'].path,
                                'model', f'{e}_{self.rank}.pt')
        self.model.load_state_dict(torch.load(model_name, map_location=self.device, weights_only=True))
        self.target_model.load_state_dict(torch.load(model_name, map_location=self.device, weights_only=True))

    def save_model(self, e):
        """
        保存模型 - 与colight.py保持一致
        """
        path = os.path.join(Registry.mapping['logger_mapping']['path'].path, 'model')
        if not os.path.exists(path):
            os.makedirs(path)
        model_name = os.path.join(path, f'{e}_{self.rank}.pt')
        torch.save(self.target_model.state_dict(), model_name)