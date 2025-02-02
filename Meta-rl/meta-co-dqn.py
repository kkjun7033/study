import tensorflow as tf
import numpy as np
import math
import collections
import pandas as pd
import random

sample_size =32
discount = 0.9

nLink=77
nbatch = 32
nphase = 48
maskQb = tf.Variable(np.zeros([nbatch,1,nphase]), dtype=tf.float32)

def encoder_model():
    x_input = tf.keras.Input(shape=(324,)) 
    x_ = x_input
    x_ = tf.keras.layers.Flatten()(x_)
       
    x_ = tf.keras.layers.Dense(500, activation='relu')(x_)
    x_ = tf.keras.layers.Dense(300, activation='relu')(x_)
    x_ = tf.keras.layers.Dense(100, activation='relu')(x_)
    last = tf.keras.layers.Dense(6)(x_)
    model = tf.keras.Model(inputs = x_input, outputs = [last])
    return model

def product_of_gaussian(means, std_sqs):
    sigmas_squared = tf.clip_by_value(std_sqs, clip_value_min=1e-7, clip_value_max=1e+7)
    sigma_squared = 1. / tf.math.reduce_sum(tf.math.reciprocal(sigmas_squared), axis=0)
    mu = sigma_squared * tf.math.reduce_sum(means / sigmas_squared, axis=0)
    return mu, sigma_squared

def reparameterize(mean, std):
    eps = tf.random.normal(shape=tf.shape(mean))
    eps = tf.cast(eps, dtype = tf.float32)
    mean = tf.cast(mean, dtype = tf.float32)
    std = tf.cast(std, dtype = tf.float32)
    return eps * std + mean    

def infer_posterior(context):
    latent = encoder(context)
    mu = latent[:, :3]
    sigma_sq = tf.math.softplus(latent[:, 3:])
    N_m, N_s = product_of_gaussian(mu, sigma_sq)
    sample_z = reparameterize(N_m, tf.math.sqrt(N_s))
    return sample_z, N_m, N_s #tf.reshape(sample_z, [-1, 1])

def KL_div(m, v):
    prior = tfp.distributions.Normal(tf.zeros(tf.shape(m)), tf.ones(tf.shape(v)))
    posteriors = tfp.distributions.Normal(m, tf.math.sqrt(v))# for mu, v in zip(m, v)]
    kl_divs = tfp.distributions.kl_divergence(posteriors, prior)# for post in posteriors]
    loss = tf.reduce_sum(kl_divs, -1)
    return loss

def fout(m, x):
    a= tf.einsum("iab,ib->ia", m, x)
    return a

global maskQb    
def dqn_model():
    
    x_ = tf.keras.Input(shape=(77,2)) 
    z_ = tf.keras.Input(shape=(3,)) 

    x_ = tf.keras.layers.Flatten()(x_)
    z_ = tf.keras.layers.Flatten()(z_)
    x_ = tf.keras.layers.concatenate([x_, z_])
       
    x_ = tf.keras.layers.Dense(300)(x_)
    x_ = tf.keras.layers.BatchNormalization()(x_)
    x_ = tf.keras.layers.LeakyReLU(alpha=0.3)(x_) 
    
    x_ = tf.keras.layers.Dense(150)(x_)
    x_ = tf.keras.layers.BatchNormalization()(x_)
    x_ = tf.keras.layers.LeakyReLU(alpha=0.3)(x_) 
    
    x_ = tf.keras.layers.Dense(70)(x_)
    x_ = tf.keras.layers.BatchNormalization()(x_)
    x_ = tf.keras.layers.LeakyReLU(alpha=0.3)(x_)     

    x_ = tf.keras.layers.Dense(48)(x_)
    x_ = tf.keras.activations.tanh(x_)

    x_Qb = x_
    x_Qt = x_ 
    x_Qt = tf.expand_dims(x_Qt,1)

    x_Qb = fout(maskQb, x_Qb)
    
    final_model = tf.keras.Model(inputs = [x_input, z_input], outputs = [x_Qt, x_Qb] )

    return final_model
    
encoder = encoder_model()
model = dqn_model()
modelT = dqn_model()

nbatch = 32
nphase = 48
dqn_variable = model.trainable_variables + encoder.trainable_variables
Adam = tf.keras.optimizers.Adam(learning_rate=0.0001, beta_1=0.9, beta_2=0.999, epsilon=1e-08, decay=0.0) #default value of Adam

def DQN(replays):
    sample_size = 32
    replay = replays 
    
    SS = tf.convert_to_tensor(np.asarray(replay[0]))#np.asarray(replay[0]) ##6천개 sars set 중에 e번째 set 의 [0]인 s
    action = np.asarray(replay[1])
    rr  = tf.convert_to_tensor(np.asarray(replay[2]), dtype=tf.float32)#np.asarray(replay[2])
    SS_ = tf.convert_to_tensor(np.asarray(replay[3]))#np.asarray(replay[3])
    St = np.asarray(replay[4][3]) #for predict(77, 2)
    context = np.asarray(replay[5])
    
    with tf.GradientTape() as tape:
        tape.watch(dqn_variable)
        
        Z, m, v = infer_posterior(context)#np.ones((32,17)))
        task_Z = tf.repeat(tf.expand_dims(Z,0), np.shape(SS)[0], axis=0)
        bar_Z = tf.stop_gradient(task_Z)
        
        QQ, _ = modelT([SS_, bar_Z]) #targetQ selectQ1
        
        QQt = [tf.math.reduce_max(QQ[:,:,0:3], axis=2)+ tf.math.reduce_max(QQ[:,:,3:5], axis=2)+ tf.math.reduce_max(QQ[:,:,5:9], axis=2)+ tf.math.reduce_max(QQ[:,:,9:12], axis=2)+ tf.math.reduce_max(QQ[:,:,12:15], axis=2)+\
                 tf.math.reduce_max(QQ[:,:,15:19], axis=2)+ tf.math.reduce_max(QQ[:,:,19:22], axis=2)+ tf.math.reduce_max(QQ[:,:,22:26], axis=2)+ tf.math.reduce_max(QQ[:,:,26:29], axis=2)+ tf.math.reduce_max(QQ[:,:,29:32], axis=2)+\
                 tf.math.reduce_max(QQ[:,:,32:35], axis=2)+ tf.math.reduce_max(QQ[:,:,35:39], axis=2)+ tf.math.reduce_max(QQ[:,:,39:41], axis=2)+ tf.math.reduce_max(QQ[:,:,41:44], axis=2)+ tf.math.reduce_max(QQ[:,:,44:48], axis=2)] # Select a(t)
        QQt= tf.convert_to_tensor(QQt)

        Qt = tf.reshape(rr,[32,1]) + discount * tf.reshape(QQt,[32,1])  #32*1, Qt y값
        QQb=[]
        for i in range(32):
            actQ = Mmask(action[i])
            QQb.append(actQ)
        QQb=tf.convert_to_tensor(QQb, dtype=tf.float32)    #a에 해당하는 mask 값
        maskQb.assign(QQb)  # Q값을 위한 mask 변경
        _, Q1 = model([SS, task_Z])
        
        #loss = tf.reduce_mean((Q1 - Qt)**2)
        Qloss = tf.keras.losses.MSE(Qt, Q1)

        prior = tfp.distributions.Normal(tf.zeros(tf.shape(m)), tf.ones(tf.shape(v)))
        posteriors = tfp.distributions.Normal(m, tf.math.sqrt(v))# for mu, v in zip(m, v)]
        kl_divs = tfp.distributions.kl_divergence(posteriors, prior)# for post in posteriors]
        kl_loss = tf.reduce_sum(kl_divs, -1)
        
        loss = Qloss + kl_loss

    dqn_grads = tape.gradient(loss, dqn_variable)
    Adam.apply_gradients(zip(dqn_grads, dqn_variable))

    SSa=np.repeat(np.expand_dims(St,0), np.shape(SS)[0], axis=0)
    Q1, Q2 = model.predict([SSa,task_Z], batch_size=np.shape(SSa)[0], verbose=0)  #마지막 학습된 모형으로 Q값 뽑아내기.
    Qv= Q1[0:1] 

    return Qv
    
def Mmask(q):
    x=np.zeros([1,48])
    x[0][q[0]]=1
    x[0][q[1]+3]=1
    x[0][q[2]+5]=1
    x[0][q[3]+9]=1
    x[0][q[4]+12]=1
    x[0][q[5]+15]=1
    x[0][q[6]+19]=1
    x[0][q[7]+22]=1
    x[0][q[8]+26]=1
    x[0][q[9]+29]=1
    x[0][q[10]+32]=1
    x[0][q[11]+35]=1
    x[0][q[12]+39]=1
    x[0][q[13]+41]=1
    x[0][q[14]+44]=1
    return x    
   
