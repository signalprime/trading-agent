import os
import sys

newPath = os.path.dirname(os.path.abspath(os.path.dirname(os.path.abspath(os.path.dirname(os.path.abspath(os.path.dirname(__file__)))))))+ '\\trading-gym'
sys.path.append(newPath)

from gym_core import tgym
import numpy as np

from keras.models import Sequential
from keras.layers import Dense, Activation, Flatten, Input, Conv1D, Conv2D, MaxPooling1D, MaxPooling2D, Dropout, Concatenate
from keras.optimizers import Adam
from keras import models

from rl.agents import DQNAgent
from rl.memory import SequentialMemory
from rl.policy import BoltzmannQPolicy
from rl.processors import MultiInputProcessor

import logging
import time

from rl.core import Processor
from collections import deque
from rl.callbacks import Callback

EPISODES = 10000
RENDER = False
ACTION_SIZE = 2
OBSERVATION_SIZE = 111

logging.basicConfig(filename='logs/trading-agent-{}.log'.format(time.strftime('%Y%m%d%H%M%S')), level=logging.DEBUG)


class ModelIntervalCheckpoint(Callback):
    def __init__(self, filepath, interval, verbose=0):
        super(ModelIntervalCheckpoint, self).__init__()
        self.filepath = filepath
        self.interval = interval
        self.verbose = verbose
        self.total_steps = 0

    def on_episode_end(self, episode, logs={}):
        filepath = self.filepath.format(step=self.total_steps, **logs)

        if filepath.endswith('.h5f'):
            path = filepath[:filepath.rfind('/')]
        else:
            path = filepath
        import os
        if not os.path.exists(path):
            os.makedirs(path)

        self.model.save_weights(filepath, overwrite=True)

    def on_step_end(self, step, logs={}):
        pass


class MyTGym(tgym.TradingGymEnv):
    holder_observation = deque(np.array([[0 for x in range(52)] for y in range(60)]), maxlen=60)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.price_holder = deque(maxlen=60)

    def _rewards(self, observation, action, done, info):
        self.price_holder.append([action, observation[31]])
        if len(self.price_holder) == 60:
            if self.price_holder[0][0]:
                reward = 0
                for data in self.price_holder:
                    reward += (data[1] - self.price_holder[0][1])
                return reward / 60
            else:
                return 0
        else:
            return 0

    def observation_processor(self, observation):
        self.holder_observation.append(observation)
        # print('observation.shape : ', observation.shape)
        # print(np.array([100 * x for x in range(60)]))
        return [[100 * x] for x in range(60)], [[[-x, -2*x] for x in range(20)] for y in range(60)], \
               [[x for x in range(11)] for y in range(60)]


class MyProcessor(MultiInputProcessor):
    def process_state_batch(self, state_batch):
        print(state_batch)
        print()
        input_batches = [[] for x in range(self.nb_inputs)]
        for state in state_batch:
            processed_state = [[] for x in range(self.nb_inputs)]
            for observation in state:
                assert len(observation) == self.nb_inputs
                for o, s in zip(observation, processed_state):
                    s.append(o)
            for idx, s in enumerate(processed_state):
                if idx == 0 or 1:
                    input_batches[idx].append(s[0])
                else:
                    input_batches[idx].append(s)
        print('------------')
        for x in input_batches:
            print(x)
            print()
        # print([np.array(x) for x in input_batches])
        print('#############')
        return [np.array(x) for x in input_batches]


def build_network():

    # price history
    i1 = Input(shape=(60, 1))  # 60 features 1 channel
    h1 = Conv1D(32, kernel_size=4, activation='relu')(i1)
    h1 = Conv1D(64, kernel_size=4, activation='relu')(h1)
    h1 = MaxPooling1D(pool_size=4)(h1)
    h1 = Dropout(0.3)(h1)
    h1 = Flatten()(h1)

    # order book history
    i2 = Input(shape=(60, 20, 2))  # 2 x 20 features 60 channels
    h2_1 = Conv2D(32, kernel_size=(2, 1), activation='relu')(i2)
    h2_1 = MaxPooling2D(pool_size=(1, 4))(h2_1)
    h2_1 = Dropout(0.3)(h2_1)
    h2_1 = Flatten()(h2_1)
    h2_2 = Conv2D(32, kernel_size=(1, 2), activation='relu')(i2)
    h2_2 = MaxPooling2D(pool_size=(2, 4))(h2_2)
    h2_2 = Dropout(0.3)(h2_2)
    h2_2 = Flatten()(h2_2)
    h2 = Concatenate()([h2_1, h2_2])

    # transaction history
    i3 = Input(shape=(60, 11))  # 60 features 11 channels
    h3 = Conv1D(32, kernel_size=4, activation='relu')(i3)
    h3 = Conv1D(64, kernel_size=4, activation='relu')(h3)
    h3 = MaxPooling1D(pool_size=4)(h3)
    h3 = Dropout(0.3)(h3)
    h3 = Flatten()(h3)

    # concatenate
    h = Concatenate()([h1, h2])
    h = Concatenate()([h, h3])

    h = Activation('relu')(Dense(64)(h))
    h = Dropout(0.3)(h)
    h = Activation('relu')(Dense(24)(h))
    h = Dropout(0.3)(h)
    y = Activation('linear')(Dense(2)(h))

    model = models.Model([i1, i2, i3], y)
    model.compile(loss='binary_crossentropy', optimizer='adam', metrics=['accuracy'])
    model.summary()

    return model

if __name__ == '__main__':

    logging.debug('start.')
    env = MyTGym(episode_type='0', percent_goal_profit=2, percent_stop_loss=5, episode_duration_min=60)

    memory = SequentialMemory(limit=50000, window_length=1)
    policy = BoltzmannQPolicy()
    model = build_network()

    logging.debug('dqn agent start..')

    model_path = 'save_model/{}_weights.h5f'.format('buy_signal_agent')
    chk_point = ModelIntervalCheckpoint(filepath=model_path, interval=50000)
    # processor = MultiInputProcessor(nb_inputs=3)
    processor = MyProcessor(nb_inputs=3)

    dqn = DQNAgent(model=model, nb_actions=2, memory=memory, nb_steps_warmup=60,
                   target_model_update=1e-2, policy=policy, processor=processor)

    dqn.compile(Adam(lr=1e-3), metrics=['mae'])

    # dqn.load_weights(model_path)
    # dqn.load_weights('dqn_{}_weights.h5f'.format('trading'))

    # Okay, now it's time to learn something! We visualize the training here for show, but this
    # slows down training quite a lot. You can always safely abort the training prematurely using
    # Ctrl + C.
    while True:
        dqn.fit(env, nb_steps=50000, visualize=False, verbose=2, callbacks=[chk_point])

        # After training is done, we save the final weights.
        dqn.save_weights(model_path, overwrite=True)
        # dqn.save_weights('dqn_{}_weights.h5f'.format('trading'), overwrite=True)

        # Finally, evaluate our algorithm for 5 episodes.
        dqn.test(env, nb_episodes=5, visualize=True)
