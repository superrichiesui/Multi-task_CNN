from __future__ import division
import tensorflow as tf
import pprint
import random
import numpy as np
import os, glob
import utils_lr as utlr


class DataLoader(object):
    def __init__(self,
                 dataset_dir,
                 batch_size,
                 image_height,
                 image_width,
                 split,
                 opt):
        self.dataset_dir=dataset_dir
        self.batch_size=batch_size
        self.image_height=image_height
        self.image_width=image_width
        self.split=split
        self.opt = opt



    #==================================
    # Load training data from tf records
    #==================================

    def inputs(self,batch_size, num_epochs,with_aug=False):
        """Reads input data num_epochs times.
        Args:
            train: Selects between the training (True) and validation (False) data.
            batch_size: Number of examples per returned batch.
            num_epochs: Number of times to read the input data, or 0/None to
            train forever.
        Returns:
            A tuple (images, labels), where:
            * images is a float tensor with shape [batch_size, mnist.IMAGE_PIXELS]
            in the range [-0.5, 0.5].
            * labels is an int32 tensor with shape [batch_size] with the true label,
            a number in the range [0, mnist.NUM_CLASSES).
            This function creates a one_shot_iterator, meaning that it will only iterate
            over the dataset once. On the other hand there is no special initialization
            required.
        """
        def decode(serialized_example):
            """Parses an image and label from the given `serialized_example`."""
            features = tf.parse_single_example(
                serialized_example,
                # Defaults are not specified since both keys are required.
                features={
                    'color': tf.FixedLenFeature([], tf.string),
                    'IR': tf.FixedLenFeature([], tf.string),
                    'depth': tf.FixedLenFeature([], tf.string),
                    'mask': tf.FixedLenFeature([], tf.string),
				    'quaternion': tf.FixedLenFeature([], tf.string),
				    'translation': tf.FixedLenFeature([], tf.string),
                    'landmark_heatmap': tf.FixedLenFeature([], tf.string),
                    'visibility': tf.FixedLenFeature([], tf.string),
                    'matK': tf.FixedLenFeature([], tf.string),
                    'H': tf.FixedLenFeature([], tf.string),
                    'points2D': tf.FixedLenFeature([], tf.string),
                })

            # Convert from a scalar string tensor (whose single string has
            # length mnist.IMAGE_PIXELS) to a uint8 tensor with shape
            # [mnist.IMAGE_PIXELS].
            image = tf.decode_raw(features['color'], tf.float64)
            IR = tf.decode_raw(features['IR'], tf.float32)
            depth = tf.decode_raw(features['depth'], tf.float32)#/100.0
            label = tf.decode_raw(features['mask'], tf.uint8)
            quaternion = tf.decode_raw(features['quaternion'], tf.float64)
            translation = tf.decode_raw(features['translation'], tf.float64)
            points2D = tf.decode_raw(features['landmark_heatmap'], tf.float32)
            visibility = tf.decode_raw(features['visibility'], tf.float32)
            matK = tf.decode_raw(features['matK'], tf.float64)
            H = tf.decode_raw(features['H'], tf.float64)
            pixel_coords = tf.decode_raw(features['points2D'], tf.float64)

            image =  tf.cast(tf.reshape(image,[self.image_height, self.image_width, 3]),tf.float32)/255.0-0.5

            IR = tf.cast(tf.reshape(IR,[self.image_height, self.image_width, 3]),tf.float32)/255.0-0.5
            
            IR = tf.expand_dims(IR[:,:,0],axis=2)

            depth = tf.cast(tf.reshape(depth,[self.image_height, self.image_width, 1]),tf.float32)
            label = tf.reshape(label,[self.image_height, self.image_width, 1])
            quaternion = tf.cast(tf.reshape(quaternion,[4]),tf.float32)

            translation = tf.cast(tf.reshape(translation,[3]),tf.float32)
            #import pdb;pdb.set_trace()
            norm = tf.sqrt(tf.reduce_sum(tf.square(translation),0, keep_dims=True))
            translation = translation / norm
            translation = tf.concat([translation,norm],axis=0)
            
            #import pdb;pdb.set_trace()
            points2D = tf.reshape(points2D,[self.image_height, self.image_width,28])#*(self.image_height*self.image_width)/10.0
            div = tf.tile(tf.expand_dims(tf.expand_dims(tf.reduce_max(points2D,[0,1])+0.0000001,axis=0),axis=1),[self.image_height,self.image_width,1])
            points2D = points2D/div
            #points2D = points2D*(self.image_height*self.image_width)

            pixel_coords = tf.cast(tf.reshape(pixel_coords,[2,28]),dtype=tf.float32)

            if self.opt.downsample:
                image = tf.image.resize_images(image,[224,224])
                IR = tf.image.resize_images(IR,[224,224])


            visibility.set_shape([28])
            visibility = tf.cast(visibility,tf.float32)
            matK = tf.cast(tf.reshape(matK,[3,3]),tf.float32)

            # Convert label from a scalar uint8 tensor to an int32 scalar.
            label = tf.cast(label, tf.float32)/255.0



            #Data augmentationmamatK
            data_dict = {}
            data_dict['image'] = image
            data_dict['IR'] = IR
            data_dict['depth'] = depth
            data_dict['label'] = label
            data_dict['quaternion'] = quaternion
            data_dict['translation'] = translation
            data_dict['points2D'] = points2D
            data_dict['visibility'] = visibility
            data_dict['matK'] = matK
            data_dict['pixel_coords'] = pixel_coords

            data_dict = self.data_augmentation2(data_dict,self.image_height,self.image_width)

            return data_dict

        def augment(data_dict):
        
            ir_batch, image_batch, depth_batch, label_batch,landmark_batch,matK = self.data_augmentation(
                                                                                    data_dict['IR'], 
                                                                                    data_dict['image'], 
                                                                                    data_dict['depth'],
                                                                                    data_dict['label'], 
                                                                                    data_dict['points2D'],
                                                                                    data_dict['matK'],
                                                                                    self.image_height,
                                                                                    self.image_width)
            data_dict['image'] = image_batch
            data_dict['depth'] = depth_batch
            data_dict['label'] = label_batch
            data_dict['points2D'] = landmark_batch
            data_dict['IR'] = ir_batch
            data_dict['matK'] = matK
            
            return data_dict
        def augment2(data_dict):
            data_dict = self.data_augmentation2(data_dict,self.image_height,self.image_width)

        if not num_epochs:
            num_epochs = None
        filenames = glob.glob(os.path.join(self.dataset_dir,'*.tfrecords'))

        with tf.name_scope('input'):
            # TFRecordDataset opens a binary file and reads one record at a time.
            # `filename` could also be a list of filenames, which will be read in order.
            dataset = tf.data.TFRecordDataset(filenames)

            # The map transformation takes a function and applies it to every element
            # of the dataset.
            dataset = dataset.map(decode,num_parallel_calls=8)
            #dataset = dataset.map(augment2)
            # dataset = dataset.map(normalize)

            # The shuffle transformation uses a finite-sized buffer to shuffle elements
            # in memory. The parameter is the number of elements in the buffer. For
            # completely uniform shuffling, set the parameter to be the same as the
            # number of elements in the dataset.
            dataset = dataset.shuffle(100)#1000 + 3 * batch_size)
            dataset = dataset.repeat(num_epochs)
            dataset = dataset.batch(batch_size)
            #if with_aug is not None:
            #dataset = dataset.map(augment)

            #iterator = dataset.make_one_shot_iterator()
        return dataset#iterator.get_next()


    #==================================
    # Load training data from tf records
    #==================================

    def inputs_test(self,batch_size, num_epochs,with_aug=False):
        """Reads input data num_epochs times.
        Args:
            train: Selects between the training (True) and validation (False) data.
            batch_size: Number of examples per returned batch.
            num_epochs: Number of times to read the input data, or 0/None to
            train forever.
        Returns:
            A tuple (images, labels), where:
            * images is a float tensor with shape [batch_size, mnist.IMAGE_PIXELS]
            in the range [-0.5, 0.5].
            * labels is an int32 tensor with shape [batch_size] with the true label,
            a number in the range [0, mnist.NUM_CLASSES).
            This function creates a one_shot_iterator, meaning that it will only iterate
            over the dataset once. On the other hand there is no special initialization
            required.
        """
        def decode(serialized_example):
            """Parses an image and label from the given `serialized_example`."""
            features = tf.parse_single_example(
                serialized_example,
                # Defaults are not specified since both keys are required.
                features={
                    'color': tf.FixedLenFeature([], tf.string),
                    'IR': tf.FixedLenFeature([], tf.string),
                    'depth': tf.FixedLenFeature([], tf.string),
                    'matK': tf.FixedLenFeature([], tf.string),
                })

            # Convert from a scalar string tensor (whose single string has
            # length mnist.IMAGE_PIXELS) to a uint8 tensor with shape
            # [mnist.IMAGE_PIXELS].
            image = tf.decode_raw(features['color'], tf.float64)/255.0-0.5
            IR = tf.decode_raw(features['IR'], tf.float32)/255.0-0.5
            
            depth = tf.decode_raw(features['depth'], tf.float32)#/100.0
            matK = tf.decode_raw(features['matK'], tf.float64)

            image =  tf.cast(tf.reshape(image,[self.image_height, self.image_width, 3]),tf.float32)
            IR = tf.cast(tf.reshape(IR,[self.image_height, self.image_width, 3]),tf.float32)
            IR = tf.expand_dims(IR[:,:,0],axis=2)
            depth = tf.cast(tf.reshape(depth,[self.image_height, self.image_width, 1]),tf.float32)
            matK = tf.cast(tf.reshape(matK,[3,3]),tf.float32)

            if self.opt.downsample:
                image = tf.image.resize_images(image,[224,224])
                IR = tf.image.resize_images(IR,[224,224])

            #Data augmentationmamatK
            data_dict = {}
            data_dict['image'] = image
            data_dict['IR'] = IR
            data_dict['depth'] = depth
            data_dict['matK'] = matK

            return data_dict


        if not num_epochs:
            num_epochs = None
        filenames = glob.glob(os.path.join(self.dataset_dir,'*.tfrecords'))

        with tf.name_scope('input_test'):
            # TFRecordDataset opens a binary file and reads one record at a time.
            # `filename` could also be a list of filenames, which will be read in order.
            dataset = tf.data.TFRecordDataset(filenames)

            # The map transformation takes a function and applies it to every element
            # of the dataset.
            dataset = dataset.map(decode)
            # dataset = dataset.map(augment)
            # dataset = dataset.map(normalize)

            # The shuffle transformation uses a finite-sized buffer to shuffle elements
            # in memory. The parameter is the number of elements in the buffer. For
            # completely uniform shuffling, set the parameter to be the same as the
            # number of elements in the dataset.
            dataset = dataset.shuffle(1000)#1000 + 3 * batch_size)
            dataset = dataset.repeat(num_epochs)
            dataset = dataset.batch(batch_size)
            iterator = dataset.make_one_shot_iterator()

        return iterator.get_next()


    #================================
    # Load rgb, depth, and mask through txt
    #================================
    def load_data_batch(self,split):

        # Reads pfathes of images together with their labels
        image_list,depth_list,label_list,ir_list,landmark_list = self.read_labeled_image_list(split)
        steps_per_epoch = int(len(image_list)//self.batch_size)

        #import pdb;pdb.set_trace()
        images = tf.convert_to_tensor(image_list, dtype=tf.string)
        depths = tf.convert_to_tensor(depth_list, dtype=tf.string)
        labels = tf.convert_to_tensor(label_list, dtype=tf.string)
        irs = tf.convert_to_tensor(ir_list, dtype=tf.string)
        landmarks = tf.convert_to_tensor(landmark_list, dtype=tf.string)

        # Makes an input queue
        input_queue = tf.train.slice_input_producer([images,depths,labels,irs,landmarks], 
                                                    num_epochs = 900,
                                                    shuffle=True)

        image,depth,label = self.read_images_from_disk(input_queue)

        # Optional Image and Label Batching
        image.set_shape((self.image_height, self.image_width, 3))
        depth.set_shape([self.image_height, self.image_width, 1])
        label.set_shape([self.image_height, self.image_width, 1])
        image_batch, depth_batch, label_batch = tf.train.batch([image,depth,label],
                                    num_threads = 8, batch_size=self.batch_size)

        # Data augmentation
        if split=='train':
            image_batch, depth_batch, label_batch = self.data_augmentation(image_batch, depth_batch, label_batch,224,224)
        
        return image_batch, depth_batch, label_batch, steps_per_epoch





    #===================================
    # Get file name list
    #===================================

    def read_labeled_image_list(self,split):
        """Reads a .txt file containing pathes and labeles
        Args:
           image_list_file: a .txt file with one /path/to/image per line
           label: optionally, if set label will be pasted after each line
        Returns:
           List with all filenames in file image_list_file
        """
        
        f = open(self.dataset_dir+'/'+split+'.txt', 'r')
        colorimages = []
        depthimages = []
        labelnames = []
        irnames = []
        landmarknames = []

        

        for line in f:

            basepath = line[:-8]
            name = line[-8:-1]

            colorimage = basepath+'\\color\\'+name+'color.png.color.png'
            colorimages.append(colorimage)

            depthimage = line[:-1]+'depth1.png'
            depthimages.append(depthimage)

            # irimage = line[:-1]+'ir.png'
            # irnames.append(irimage)
            
            if split=='train' or split=='valid':
                labelname = basepath+'\\mask\\'+name+'color.png.landmark_filtered.png'
                labelnames.append(labelname)
                #landmarkname = basepath+'\\landmark\\'+name+'landmark.txt'
                #landmarknames.append(landmarkname)
                
            else:
                labelname = line[:-1]+'depth0.png'
                labelnames.append(labelname)               

        return colorimages,depthimages,labelnames#,irnames,landmarknames


    def read_images_from_disk(self,input_queue):
        """Consumes a single filename and label as a ' '-delimited string.
        Args:
          filename_and_label_tensor: A scalar string tensor.
        Returns:
          Two tensors: the decoded image, and the string label.
        """

        #import pdb;pdb.set_trace()
        image_file = tf.read_file(input_queue[0])
        depth_file = tf.read_file(input_queue[1])
        label_file = tf.read_file(input_queue[2])
        ir_file = tf.read_file(input_queue[3])
        landmark_file = tf.read_file(input_queue[4])


        image = tf.to_float(tf.image.resize_images(tf.image.decode_png(image_file),[224,224]))

        depth = tf.to_float(tf.image.resize_images(tf.image.decode_png(depth_file,dtype=tf.uint16),[224,224]))

        label = tf.to_float(tf.image.resize_images(tf.image.decode_png(label_file),[224,224]))

        ir = tf.to_float(tf.image.resize_images(tf.image.decode_png(ir_file),[224,224]))

        #record_defaults = [[0.0]]*
        #proj_landmark_vis = 

        image = image/255.0

        depth = depth/1600.0

        label = tf.expand_dims(label[:,:,0],2)

        label = label/255.0

        ir = ir/255.0

        return image, depth, label


    def data_augmentation(self, ir, image, depth, label, landmark,matK, out_h, out_w):

        def _random_true_false():
            prob = tf.random_uniform(shape=[], minval=0., maxval=1., dtype=tf.float32)
            predicate = tf.less(prob, 0.5)
            return predicate

        # Random scaling
        def random_scaling(ir, image, depth, label,landmark):
            batch_size, in_h, in_w, _ = image.get_shape().as_list()
            scaling = tf.random_uniform([2], 1, 1.15)
            x_scaling = scaling[0]
            y_scaling = scaling[1]
            out_h = tf.cast(in_h * y_scaling, dtype=tf.int32)
            out_w = tf.cast(in_w * x_scaling, dtype=tf.int32)

            #matK[:,0,0] = matK[:,0,0]

            image = tf.image.resize_area(image, [out_h, out_w])
            depth = tf.image.resize_area(depth, [out_h, out_w])
            label = tf.image.resize_area(label, [out_h, out_w])
            ir = tf.image.resize_area(ir, [out_h, out_w])
            landmark = tf.image.resize_area(landmark, [out_h, out_w])
            return ir, image, depth, label,landmark

        # Random cropping
        def random_cropping(ir, image, depth, label,landmark,matK, out_h, out_w):

            
            # batch_size, in_h, in_w, _ = im.get_shape().as_list()
            batch_size, in_h, in_w, _ = tf.unstack(tf.shape(image))
            offset_y = tf.random_uniform([1], 0, in_h - out_h + 1, dtype=tf.int32)[0]
            offset_x = tf.random_uniform([1], 0, in_w - out_w + 1, dtype=tf.int32)[0]

            _in_h = tf.to_float(in_h)
            _in_w = tf.to_float(in_w)
            _out_h = tf.to_float(out_h)
            _out_w = tf.to_float(out_w)
            fx = matK[:,0,0]*_in_w/_out_w
            fy = matK[:,1,1]*_in_h/_out_h
            cx = matK[:,0,2]*_in_w/_out_w-tf.to_float(offset_x)
            cy = matK[:,1,2]*_in_h/_out_h-tf.to_float(offset_y)
            
            zeros = tf.zeros_like(fx)
            ones = tf.ones_like(fx)

            image = tf.image.crop_to_bounding_box(
                image, offset_y, offset_x, out_h, out_w)
            depth = tf.image.crop_to_bounding_box(
                depth, offset_y, offset_x, out_h, out_w)
            label = tf.image.crop_to_bounding_box(
                label, offset_y, offset_x, out_h, out_w)
            landmark = tf.image.crop_to_bounding_box(
                landmark, offset_y, offset_x, out_h, out_w)
            ir = tf.image.crop_to_bounding_box(
                ir, offset_y, offset_x, out_h, out_w)

            matK = tf.stack([tf.stack([fx,zeros,cx],axis=1),
                            tf.stack([zeros,fy,cy],axis=1),
                            tf.stack([zeros,zeros,ones],axis=1)],axis=1)
                
            return ir, image, depth, label, landmark, matK

        # Random flip
        def random_flip(ir, image, depth, label,landmark,matK,out_h,out_w):
            # batch_size, in_h, in_w, _ = im.get_shape().as_list()
            
            fx = matK[:,0,0]
            fy = matK[:,1,1]
            cx = matK[:,0,2]
            cy = matK[:,1,2]
            zeros = tf.zeros_like(fx)
            ones = tf.ones_like(fx)


            flip1 = _random_true_false()
            image = tf.cond(flip1, lambda:tf.image.flip_left_right(image),lambda:image)
            depth = tf.cond(flip1, lambda:tf.image.flip_left_right(depth),lambda:depth)
            label = tf.cond(flip1, lambda:tf.image.flip_left_right(label),lambda:label)
            landmark = tf.cond(flip1, lambda:tf.image.flip_left_right(landmark),lambda:landmark)
            ir = tf.cond(flip1, lambda:tf.image.flip_left_right(ir),lambda:ir)
            cx = tf.cond(flip1, lambda:out_w-cx,lambda:cx)


            flip2 = _random_true_false()
            image = tf.cond(flip2, lambda:tf.image.flip_up_down(image),lambda:image)
            depth = tf.cond(flip2, lambda:tf.image.flip_up_down(depth),lambda:depth)
            label = tf.cond(flip2, lambda:tf.image.flip_up_down(label),lambda:label)
            landmark = tf.cond(flip2, lambda:tf.image.flip_up_down(landmark),lambda:landmark)
            ir = tf.cond(flip2, lambda:tf.image.flip_up_down(ir),lambda:ir)
            cy = tf.cond(flip2, lambda:out_h-cy,lambda:cy)

            #import pdb;pdb.set_trace()
            matK = tf.stack([tf.stack([fx,zeros,cx],axis=1),
                            tf.stack([zeros,fy,cy],axis=1),
                            tf.stack([zeros,zeros,ones],axis=1)],axis=1)

            return ir,image, depth, label,landmark,matK

        def random_color(image):

            color_ordering = scaling = tf.random_uniform([1], 0, 4,dtype=tf.int32)
            
            image = tf.cond(tf.equal(color_ordering[0],tf.zeros([],tf.int32)),lambda:tf.image.random_brightness(image, max_delta=32. / 255.),lambda:image)
            image = tf.cond(tf.equal(color_ordering[0],tf.zeros([],tf.int32)),lambda:tf.image.random_saturation(image, lower=0.5, upper=1.5),lambda:image)
            image = tf.cond(tf.equal(color_ordering[0],tf.zeros([],tf.int32)),lambda:tf.image.random_hue(image, max_delta=0.2),lambda:image)
            image = tf.cond(tf.equal(color_ordering[0],tf.zeros([],tf.int32)),lambda:tf.image.random_contrast(image, lower=0.5, upper=1.5),lambda:image)

            image = tf.cond(tf.equal(color_ordering[0],tf.ones([],tf.int32)),lambda:tf.image.random_saturation(image, lower=0.5, upper=1.5),lambda:image)
            image = tf.cond(tf.equal(color_ordering[0],tf.ones([],tf.int32)),lambda:tf.image.random_brightness(image, max_delta=32. / 255.),lambda:image)
            image = tf.cond(tf.equal(color_ordering[0],tf.ones([],tf.int32)),lambda:tf.image.random_contrast(image, lower=0.5, upper=1.5),lambda:image)
            image = tf.cond(tf.equal(color_ordering[0],tf.ones([],tf.int32)),lambda:tf.image.random_hue(image, max_delta=0.2),lambda:image)

            image = tf.cond(tf.equal(color_ordering[0],tf.ones([],tf.int32)*2),lambda:tf.image.random_contrast(image, lower=0.5, upper=1.5),lambda:image)
            image = tf.cond(tf.equal(color_ordering[0],tf.ones([],tf.int32)*2),lambda:tf.image.random_hue(image, max_delta=0.2),lambda:image)
            image = tf.cond(tf.equal(color_ordering[0],tf.ones([],tf.int32)*2),lambda:tf.image.random_brightness(image, max_delta=32. / 255.),lambda:image)
            image = tf.cond(tf.equal(color_ordering[0],tf.ones([],tf.int32)*2),lambda:tf.image.random_saturation(image, lower=0.5, upper=1.5),lambda:image)

            image = tf.cond(tf.equal(color_ordering[0],tf.ones([],tf.int32)*3),lambda:tf.image.random_hue(image, max_delta=0.2),lambda:image)
            image = tf.cond(tf.equal(color_ordering[0],tf.ones([],tf.int32)*3),lambda:tf.image.random_saturation(image, lower=0.5, upper=1.5),lambda:image)
            image = tf.cond(tf.equal(color_ordering[0],tf.ones([],tf.int32)*3),lambda:tf.image.random_contrast(image, lower=0.5, upper=1.5),lambda:image)
            image = tf.cond(tf.equal(color_ordering[0],tf.ones([],tf.int32)*3),lambda:tf.image.random_brightness(image, max_delta=32. / 255.),lambda:image) 

            return image

        def do_color(ir, image, depth, label,landmark):
            image = random_color(image)
            return ir, image, depth, label,landmark

        def do_all(ir, image, depth, label,landmark,matk):
            ir, image, depth, label,landmark = random_scaling(ir, image, depth, label,landmark)
            ir, image, depth, label,landmark,matk = random_cropping(ir, image, depth, label,landmark,matk, out_h, out_w)
            ir ,image, depth, label,landmark,matk = random_flip(ir, image, depth, label,landmark,matk, out_h, out_w)
            image = random_color(image)
            return ir, image, depth, label,landmark,matk

        return do_all(ir, image, depth, label,landmark,matK)

        #return ir, image, depth, label,landmark

        

    def data_augmentation2(self, data_dict, out_h, out_w):

        def random_rotate(data_dict):
            #import pdb;pdb.set_trace()
            angle = tf.random_uniform([1], -np.pi/5.0, np.pi/5.0, dtype=tf.float32)[0]
            data_dict['IR'] = tf.contrib.image.rotate(data_dict['IR'],angle)
            data_dict['image'] = tf.contrib.image.rotate(data_dict['image'],angle)
            data_dict['points2D'] = tf.contrib.image.rotate(data_dict['points2D'],angle)
            center = tf.tile(tf.expand_dims(tf.stack([tf.to_float(self.image_width/2.0),tf.to_float(self.image_height/2.0)]),axis=1),[1,data_dict['pixel_coords'].get_shape()[1]])
            temppoint = data_dict['pixel_coords']-center
            temppoint = utlr.rotate(temppoint, -angle)
            data_dict['pixel_coords'] = temppoint+center
            return data_dict

        
        # Random scaling
        def random_scaling(data_dict):
            in_h, in_w, _ = data_dict['IR'].get_shape().as_list()
            scaling = tf.random_uniform([2], 1, 1.15)
            x_scaling = scaling[0]
            y_scaling = scaling[1]
            out_h = tf.cast(in_h * y_scaling, dtype=tf.int32)
            out_w = tf.cast(in_w * x_scaling, dtype=tf.int32)

            data_dict['IR'] = tf.image.resize_images(data_dict['IR'], [out_h, out_w])
            data_dict['image'] = tf.image.resize_images(data_dict['image'], [out_h, out_w])
            data_dict['points2D'] = tf.image.resize_images(data_dict['points2D'], [out_h, out_w])
            return data_dict



        # Random cropping
        def random_cropping(data_dict):

            # batch_size, in_h, in_w, _ = im.get_shape().as_list()
            in_h, in_w, _ = tf.unstack(tf.shape(data_dict['IR']))
            offset_y = tf.random_uniform([1], 0, in_h - out_h + 1, dtype=tf.int32)[0]
            offset_x = tf.random_uniform([1], 0, in_w - out_w + 1, dtype=tf.int32)[0]

            _in_h = tf.to_float(in_h)
            _in_w = tf.to_float(in_w)
            _out_h = tf.to_float(out_h)
            _out_w = tf.to_float(out_w)

            ratio = tf.tile(tf.expand_dims(tf.stack([tf.to_float(_in_w/_out_w),tf.to_float(_in_h/_out_h)]),axis=1),[1,data_dict['pixel_coords'].get_shape()[1]])
            offsets = tf.tile(tf.expand_dims(tf.stack([tf.to_float(offset_x),tf.to_float(offset_y)]),axis=1),[1,data_dict['pixel_coords'].get_shape()[1]])

            data_dict['pixel_coords'] = data_dict['pixel_coords']*ratio-offsets

            data_dict['IR'] = tf.image.crop_to_bounding_box(
                data_dict['IR'], offset_y, offset_x, out_h, out_w)
            data_dict['image'] = tf.image.crop_to_bounding_box(
                data_dict['image'], offset_y, offset_x, out_h, out_w)
            data_dict['points2D'] = tf.image.crop_to_bounding_box(
                data_dict['points2D'], offset_y, offset_x, out_h, out_w)
            return data_dict


        def random_color(image):

            color_ordering = tf.random_uniform([1], 0, 4,dtype=tf.int32)
            
            image = tf.cond(tf.equal(color_ordering[0],tf.zeros([],tf.int32)),lambda:tf.image.random_brightness(image, max_delta=32. / 255.),lambda:image)
            image = tf.cond(tf.equal(color_ordering[0],tf.zeros([],tf.int32)),lambda:tf.image.random_saturation(image, lower=0.5, upper=1.5),lambda:image)
            image = tf.cond(tf.equal(color_ordering[0],tf.zeros([],tf.int32)),lambda:tf.image.random_hue(image, max_delta=0.2),lambda:image)
            image = tf.cond(tf.equal(color_ordering[0],tf.zeros([],tf.int32)),lambda:tf.image.random_contrast(image, lower=0.5, upper=1.5),lambda:image)

            image = tf.cond(tf.equal(color_ordering[0],tf.ones([],tf.int32)),lambda:tf.image.random_saturation(image, lower=0.5, upper=1.5),lambda:image)
            image = tf.cond(tf.equal(color_ordering[0],tf.ones([],tf.int32)),lambda:tf.image.random_brightness(image, max_delta=32. / 255.),lambda:image)
            image = tf.cond(tf.equal(color_ordering[0],tf.ones([],tf.int32)),lambda:tf.image.random_contrast(image, lower=0.5, upper=1.5),lambda:image)
            image = tf.cond(tf.equal(color_ordering[0],tf.ones([],tf.int32)),lambda:tf.image.random_hue(image, max_delta=0.2),lambda:image)

            image = tf.cond(tf.equal(color_ordering[0],tf.ones([],tf.int32)*2),lambda:tf.image.random_contrast(image, lower=0.5, upper=1.5),lambda:image)
            image = tf.cond(tf.equal(color_ordering[0],tf.ones([],tf.int32)*2),lambda:tf.image.random_hue(image, max_delta=0.2),lambda:image)
            image = tf.cond(tf.equal(color_ordering[0],tf.ones([],tf.int32)*2),lambda:tf.image.random_brightness(image, max_delta=32. / 255.),lambda:image)
            image = tf.cond(tf.equal(color_ordering[0],tf.ones([],tf.int32)*2),lambda:tf.image.random_saturation(image, lower=0.5, upper=1.5),lambda:image)

            image = tf.cond(tf.equal(color_ordering[0],tf.ones([],tf.int32)*3),lambda:tf.image.random_hue(image, max_delta=0.2),lambda:image)
            image = tf.cond(tf.equal(color_ordering[0],tf.ones([],tf.int32)*3),lambda:tf.image.random_saturation(image, lower=0.5, upper=1.5),lambda:image)
            image = tf.cond(tf.equal(color_ordering[0],tf.ones([],tf.int32)*3),lambda:tf.image.random_contrast(image, lower=0.5, upper=1.5),lambda:image)
            image = tf.cond(tf.equal(color_ordering[0],tf.ones([],tf.int32)*3),lambda:tf.image.random_brightness(image, max_delta=32. / 255.),lambda:image) 

            return image


                
        data_dict=random_rotate(data_dict)
        data_dict=random_scaling(data_dict)
        data_dict=random_cropping(data_dict)
        #data_dict['IR'] = random_color(data_dict['IR'])

        return data_dict


