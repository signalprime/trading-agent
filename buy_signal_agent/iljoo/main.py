import os
import sys
newPath = os.path.dirname(os.path.abspath(os.path.dirname(os.path.abspath(os.path.dirname(os.path.abspath(os.path.dirname(__file__)))))))+ '\\trading-gym'
sys.path.append(newPath)

from gym_core import tgym
import numpy as np

from keras.models import Sequential
from keras.layers import Dense, Activation, Flatten
from keras.optimizers import Adam

from rl.agents import DQNAgent
from rl.memory import SequentialMemory
from rl.policy import BoltzmannQPolicy
import logging
import time

from rl.core import Processor
from collections import deque
from rl.callbacks import Callback

EPISODES = 10000
RENDER = False
ACTION_SIZE = 2
OBSERVATION_SIZE = 111

logging.basicConfig(filename='logs/trading-agent-{}.log'.format(time.strftime('%Y%m%d%H%M%S')),level=logging.DEBUG)


class ModelIntervalCheckpoint(Callback):
    def __init__(self, filepath, interval, verbose=0):
        super(ModelIntervalCheckpoint, self).__init__()
        self.filepath = filepath
        self.interval = interval
        self.verbose = verbose
        self.total_steps = 0

    def on_episode_end(self, episode, logs={}):
        pass

    def on_step_end(self, step, logs={}):
        self.total_steps += 1
        if self.total_steps % self.interval != 0:
            # Nothing to do.
            return

        filepath = self.filepath.format(step=self.total_steps, **logs)

        if self.verbose > 0:
            print('Step {}: saving model to {}'.format(self.total_steps, filepath))

        if filepath.endswith('.h5f'):
            path = filepath[:filepath.rfind('/')]
        else:
            path = filepath
        import os
        if not os.path.exists(path):
            os.makedirs(path)

        self.model.save_weights(filepath, overwrite=True)


class ObservationProcessor(Processor) :
    def __init__(self, holder_observation=None):
        if holder_observation is None:
            self.holder_observation = deque(np.array([[0 for x in range(52)] for y in range(60)]), maxlen=60)
        else:
            self.holder_observation = holder_observation

    def process_observation(self, observation):
        self.holder_observation.append(observation)
        return list(self.holder_observation)


class myTGym(tgym.TradingGymEnv):
    def _rewards(self, observation, action, done, info):
        if action == 1:
            if info['stop_loss']:
                return -1
            if info['reached_profit']:
                return 1
        return 1


def build_network():

    model = Sequential()
    model.add( Flatten(input_shape=(1,) + (60,) + (52,) )  )
    model.add(Dense(300))
    model.add(Activation('relu'))
    model.add(Dense(200))
    model.add(Activation('relu'))
    model.add(Dense(30))
    model.add(Activation('relu'))
    model.add(Dense(2))
    model.add(Activation('linear'))
    # print(model.summary())
    print(model.output._keras_shape)

    return model


if __name__ == '__main__':

    logging.debug('start.')
    env = myTGym(episode_type='0', percent_goal_profit=2, percent_stop_loss=5)
    # s1, s2, s3 = env.reset()
    # state = aggregate_state(s1, s2, s3)

    memory = SequentialMemory(limit=50000, window_length=1)
    policy = BoltzmannQPolicy()
    model  = build_network()

    logging.debug('dqn agent start..')

    model_path = 'save_model/{}_weights.h5f'.format('buy_signal_agent')
    chk_point = ModelIntervalCheckpoint(filepath=model_path, interval=50000)
    obsprocesser = ObservationProcessor()

    dqn = DQNAgent(model=model, nb_actions=2, memory=memory, nb_steps_warmup=60,
                   target_model_update=1e-2, policy=policy, processor=obsprocesser)

    dqn.compile(Adam(lr=1e-3), metrics=['mae'])

    #dqn.load_weights(model_path)
    #dqn.load_weights('dqn_{}_weights.h5f'.format('trading'))

    # Okay, now it's time to learn something! We visualize the training here for show, but this
    # slows down training quite a lot. You can always safely abort the training prematurely using
    # Ctrl + C.
    dqn.fit(env, nb_steps=50000, visualize=False, verbose=2, callbacks=[chk_point])

    # After training is done, we save the final weights.
    dqn.save_weights(model_path, overwrite=True)
    #dqn.save_weights('dqn_{}_weights.h5f'.format('trading'), overwrite=True)

    # Finally, evaluate our algorithm for 5 episodes.
    dqn.test(env, nb_episodes=5, visualize=True)
