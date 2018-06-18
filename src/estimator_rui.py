import tensorflow as tf
import numpy as np
from data_loader_direct import DataLoader
from my_losses import *
from model import *
import time
import math
import os
from smoother import Smoother
import cv2
from collections import OrderedDict


def remove_first_scope(name):
    return '/'.join(name.split('/')[1:])

def collect_vars(scope, start=None, end=None, prepend_scope=None):
    '''
    Collect variables under a scope
    '''
    vars = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, scope=scope)
    var_dict = OrderedDict()
    if isinstance(start, str):
        for i, var in enumerate(vars):
            var_name = remove_first_scope(var.op.name)
            if var_name.startswith(start):
                start = i
                break
    if isinstance(end, str):
        for i, var in enumerate(vars):
            var_name = remove_first_scope(var.op.name)
            if var_name.startswith(end):
                end = i
                break
    #import pdb;pdb.set_trace()
    for var in vars[start:end]:
        var_name = remove_first_scope(var.op.name)
        if prepend_scope is not None:
            var_name = os.path.join(prepend_scope, var_name)
        var_dict[var_name] = var
    return var_dict  



def save(sess, checkpoint_dir, step, saver):
    '''
    Save checkpoints
    '''
    model_name = 'model'
    print(" [*] Saving checkpoint to %s..." % checkpoint_dir)
    if step == 'latest':
        saver.save(sess, 
                        os.path.join(checkpoint_dir, model_name + '.latest'))
    else:
        saver.save(sess, 
                        os.path.join(checkpoint_dir, model_name),
                        global_step=step)

class estimator_rui:
    '''
    A wrapper function which create data, model and loss according to input type
    '''
    def __init__(self,flags):
        self.opt = flags

    
    def gauss_smooth(self,mask,FILTER_SIZE):
        '''
        A tensorflow gauss smooth function.
        Args:
            mask: A 'Tensor' that to be smoothed
            FILTER_SIZE: Spatial size of gaussian filter
        Output:
            A gauss smoothed 'Tensor' of same size as 'mask'
        '''
        SIGMA = 0.3*((FILTER_SIZE-1)*0.5 - 1) + 0.8#0.3*(FILTER_SIZE-1) + 0.8
        smoother = Smoother({'data':mask}, FILTER_SIZE, SIGMA)
        new_mask = smoother.get_output()

        return new_mask
  

    def construct_input(self, data_dict):
        '''
        Concatenate a multichannel input for network
        '''
        if self.opt.inputs == "all":
            input_ts = tf.concat([data_dict['IR'],data_dict['depth'],data_dict['image']],axis=3) #data_dict['depth'],
        elif self.opt.inputs == "IR_depth":
            input_ts = tf.concat([data_dict['IR'],data_dict['depth']],axis=3)
        elif self.opt.inputs == "depth_color":
            input_ts = tf.concat([data_dict['depth'],data_dict['image']],axis=3)
        elif self.opt.inputs =="IR_color":
            input_ts = tf.concat([data_dict['IR'],data_dict['image']],axis=3)
        elif self.opt.inputs =="IR":
            input_ts = data_dict['IR']
        elif self.opt.inputs =="color":
            input_ts = data_dict['image']
        elif self.opt.inputs =="depth":
            input_ts = data_dict['depth']
        
        return input_ts


    def construct_model(self, input_ts,is_training=True, is_reuse=False,scope_name="default"):
        '''
        Model selection
        '''
        with tf.variable_scope(scope_name) as scope:
            if self.opt.model=="lastdecode":
                output = disp_net(tf.cast(input_ts,tf.float32),is_training,is_reuse)
            elif self.opt.model=="single":
                output = disp_net_single(tf.cast(input_ts,tf.float32),is_training,is_reuse)
            elif self.opt.model=="pose":
                output = disp_net_single_pose(tf.cast(input_ts,tf.float32),is_training,is_reuse)
            elif self.opt.model=="multiscale":
                output = disp_net_single_multiscale(tf.cast(input_ts,tf.float32),is_training,is_reuse)
            # elif self.opt.model=="hourglass":
            #     initial_output = disp_net_initial(tf.cast(input_ts,tf.float32),is_training,is_reuse)
            #     input_ts = tf.concat([input_ts,initial_output[1]],axis=3)
            #     refine_output = disp_net_refine(tf.cast(input_ts,tf.float32),is_training,is_reuse)
            #     output = [initial_output,refine_output]
            #     data_dict["landmark_init"] = tf.concat([tf.expand_dims(data_dict["points2D"][:,:,:,0],axis=3),
            #                                             tf.expand_dims(data_dict["points2D"][:,:,:,4],axis=3),
            #                                             tf.expand_dims(data_dict["points2D"][:,:,:,10],axis=3),
            #                                             tf.expand_dims(data_dict["points2D"][:,:,:,14],axis=3)],axis=3)
            elif self.opt.model=="with_tp":
                template_image = np.repeat(np.expand_dims(cv2.imread('template_image.png').astype(np.float32),axis=0),self.opt.batch_size,0)/255.0
                tp_im = tf.constant(template_image)
                input_ts = tf.concat([input_ts,tp_im],axis=3)
                output = disp_net_single(tf.cast(input_ts,tf.float32))

            #=======================
            #Construct output
            #=======================
            if self.opt.model == "multiscale":
                pred_landmark = output[1][0]
            elif self.opt.model=="hourglass":
                pred_landmark = output[1][1]
            else:
                pred_landmark = output[1]
        
        return output,pred_landmark



    def construct_summary(self,losses,data_dict,pred_landmark):
        '''
        Create summary for tensorboard visualization
        '''
        total_loss = tf.summary.scalar('losses/total_loss', losses[0])
        seg_loss = tf.summary.scalar('losses/seg_loss', losses[1])
        landmark_loss = tf.summary.scalar('losses/landmark_loss', losses[2])
        transformation_loss = tf.summary.scalar('losses/transformation_loss', losses[3])
        vis_loss = tf.summary.scalar('losses/vis_loss', losses[4])
        image = tf.summary.image('image' , \
                            data_dict['image'])

        if self.opt.with_seg:
            tf.summary.image('gt_label' , \
                                data_dict['label'])
            tf.summary.image('pred_label' , \
                                pred[0])
                            
        # random_landmark = tf.placeholder(tf.int32)
        gt_landmark = tf.expand_dims(tf.reduce_sum(data_dict['points2D'],3),axis=3)#tf.expand_dims(data_dict['points2D'][:,:,:,random_landmark],axis=3)#
        pred_landmark = tf.expand_dims(tf.reduce_sum(pred_landmark,3),axis=3)#tf.expand_dims(pred_landmark[:,:,:,random_landmark],axis=3)#
        landmark_sum = tf.summary.image('gt_lm_img' , \
                            gt_landmark)
        pred_landmark_sum = tf.summary.image('pred_lm_img' , \
                            pred_landmark)
        #return tf.summary.merge([total_loss,seg_loss,landmark_loss,transformation_loss,vis_loss,image,landmark_sum,pred_landmark_sum]) #

        
    def forward_wrapper(self,dataset_dir,scope_name=None,num_epochs=None,is_training=True, is_reuse=False,with_loss=True,with_dataaug=False,test_input=False):
        '''
        A wrapper function which create a dataloader, construct a network model and compute loss
        '''
        #Initialize data loader
        imageloader = DataLoader(dataset_dir, 
                                    5,
                                    self.opt.img_height, 
                                    self.opt.img_width,
                                    'train')
        # Load training data
        if test_input:
            data_dict = imageloader.inputs_test(self.opt.batch_size,num_epochs,with_dataaug)
        else:
            data_dict = imageloader.inputs(self.opt.batch_size,num_epochs,with_dataaug)  # batch_size, num_epochs

        #Construct input accordingly
        input_ts = self.construct_input(data_dict)

        #Select model accordingly
        output,pred_landmark = self.construct_model(input_ts,is_training, is_reuse,scope_name)

        #Compute loss accordingly
        if with_loss:
            losses = compute_loss(output,data_dict,self.opt)
        else:
            losses = 0

        return losses, pred_landmark, output, data_dict
        