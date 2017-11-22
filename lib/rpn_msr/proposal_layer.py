# --------------------------------------------------------
# Faster R-CNN
# Copyright (c) 2015 Microsoft
# Licensed under The MIT License [see LICENSE for details]
# Written by Ross Girshick and Sean Bell
# --------------------------------------------------------

import numpy as np
import yaml

from .generate_anchors import generate_anchors

# TODO: make fast_rcnn irrelevant
# >>>> obsolete, because it depends on sth outside of this project
from ..fast_rcnn.config import cfg
from ..fast_rcnn.bbox_transform import bbox_transform_inv, clip_boxes
from ..fast_rcnn.nms_wrapper import nms
# <<<< obsolete


DEBUG = False
"""
Outputs object detection proposals by applying estimated bounding-box
transformations to a set of regular boxes (called "anchors").
"""
def proposal_layer(rpn_cls_prob_reshape_P2, rpn_bbox_pred_P2, \
                   rpn_cls_prob_reshape_P3, rpn_bbox_pred_P3, \
                   rpn_cls_prob_reshape_P4, rpn_bbox_pred_P4, \
                   rpn_cls_prob_reshape_P5, rpn_bbox_pred_P5, \
                   rpn_cls_prob_reshape_P6, rpn_bbox_pred_P6, \
                   im_info, cfg_key, _feat_strides = [4, 8, 16, 32, 64], \
                   anchor_sizes = [32, 64, 128, 256, 512]): # anchor_scales = [8, 8, 8, 8, 8]
    """
    Parameters
    ----------
    rpn_cls_prob_reshape_P: (1 , H(P), W(P), A(P)x2) outputs of RPN, prob of bg or fg on pyramid layer P
    rpn_bbox_pred_P: (1 , H(P), W(P), A(P)x4), rgs boxes output of RPN on pyramid layer P
    im_info: a list of [image_height, image_width, scale_ratios]
    cfg_key: 'TRAIN' or 'TEST'
    _feat_strides: the downsampling ratio of feature map to the original input image on each pyramid layer
    anchor_sizes: the absolute anchor sizes on each pyramid layer
    ----------
    Returns
    ----------
    rpn_rois : (sum(H x W x A), 5) e.g. [0, x1, y1, x2, y2]

    # Algorithm:
    #
    # for each (H, W) location i
    #   generate A anchor boxes centered on cell i
    #   apply predicted bbox deltas at cell i to each of the A anchors
    # clip predicted boxes to image
    # remove predicted boxes with either height or width < threshold
    # sort all (proposal, score) pairs by score from highest to lowest
    # take top pre_nms_topN proposals before NMS
    # apply NMS with threshold 0.7 to remaining proposals
    # take after_nms_topN proposals after NMS
    # return the top proposals (-> RoIs top, scores top)
    #layer_params = yaml.load(self.param_str_)

    """
    anchor_scales = np.array(anchor_sizes) / np.array(_feat_strides)

    # _anchors = [generate_anchors(base_size=_feat_stride, scales=[anchor_scale]) for _feat_stride, anchor_scale in zip(_feat_strides, anchor_scales)]
    _anchors = [[], [], [], [], []]
    _anchors[0] = generate_anchors(base_size=_feat_strides[0], scales=np.array([anchor_scales[0]]))
    _anchors[1] = generate_anchors(base_size=_feat_strides[1], scales=np.array([anchor_scales[1]]))
    _anchors[2] = generate_anchors(base_size=_feat_strides[2], scales=np.array([anchor_scales[2]]))
    _anchors[3] = generate_anchors(base_size=_feat_strides[3], scales=np.array([anchor_scales[3]]))
    _anchors[4] = generate_anchors(base_size=_feat_strides[4], scales=np.array([anchor_scales[4]]))

    _num_anchors = [anchor.shape[0] for anchor in _anchors]

    im_info = im_info[0]

    #assert rpn_cls_prob_reshape.shape[0] == 1, \
    #    'Only single item batches are supported'
    # cfg_key = str(self.phase) # either 'TRAIN' or 'TEST'
    #cfg_key = 'TEST'
    pre_nms_topN  = cfg[cfg_key].RPN_PRE_NMS_TOP_N
    post_nms_topN = cfg[cfg_key].RPN_POST_NMS_TOP_N
    nms_thresh    = cfg[cfg_key].RPN_NMS_THRESH
    min_size      = cfg[cfg_key].RPN_MIN_SIZE

    rpn_cls_prob_reshapes = [rpn_cls_prob_reshape_P2, rpn_cls_prob_reshape_P3, rpn_cls_prob_reshape_P4, rpn_cls_prob_reshape_P5, rpn_cls_prob_reshape_P6]
    bbox_deltas = [rpn_bbox_pred_P2, rpn_bbox_pred_P3, rpn_bbox_pred_P4, rpn_bbox_pred_P5, rpn_bbox_pred_P6]

    heights = [rpn_cls_prob_reshape.shape[1] for rpn_cls_prob_reshape in rpn_cls_prob_reshapes]
    widths = [rpn_cls_prob_reshape.shape[2] for rpn_cls_prob_reshape in rpn_cls_prob_reshapes]

    # the first set of _num_anchors channels are bg probs
    # the second set are the fg probs, which we want
    # (4, 1, H, W, A(x))  --> (1, H, W, stack(A))
    scores = [np.reshape(np.reshape(rpn_cls_prob_reshape, [1, height, width, _num_anchor, 2])[:,:,:,:,1],
                [-1, 1])
                for height, width, rpn_cls_prob_reshape, _num_anchor in
                zip(heights, widths, rpn_cls_prob_reshapes, _num_anchors)]

    # scores are (1 * H(P) * W(P) * A(P), 1) format
    # reshape to (sum(1 * H * W * A), 1) where rows are ordered by (h, w, a)
    scores = np.concatenate(scores, axis=0)

    if DEBUG:
        print 'im_size: ({}, {})'.format(im_info[0], im_info[1])
        print 'scale: {}'.format(im_info[2])

    # 1. Generate proposals from bbox deltas and shifted anchors
    if DEBUG:
        print 'score map size: {}'.format(scores.shape)

    def gen_shift(height, width, _feat_stride):
        # Enumerate all shifts
        shift_x = np.arange(0, width) * _feat_stride
        shift_y = np.arange(0, height) * _feat_stride
        shift_x, shift_y = np.meshgrid(shift_x, shift_y)
        shift = np.vstack((shift_x.ravel(), shift_y.ravel(),
                            shift_x.ravel(), shift_y.ravel())).transpose()
        return shift

    shifts = [gen_shift(height, width, _feat_stride)
              for height, width, _feat_stride in zip(heights, widths, _feat_strides)]

    # Enumerate all shifted anchors:
    #
    # add A anchors (4, 1, A(x), 4) to
    # cell K shifts (4, K, 1, 4) to get
    # shift anchors (4, K, A(x), 4)
    # reshape to (K*stack(A), 4) shifted anchors
    As = _num_anchors
    Ks = [shift.shape[0] for shift in shifts]
    anchors = [_anchor.reshape((1, A, 4)) +
               shift.reshape((1, K, 4)).transpose((1, 0, 2))
               for A, K, _anchor, shift in zip(As, Ks, _anchors, shifts)]
    anchors = [anchor.reshape((K * A, 4))
               for anchor, A, K in zip(anchors, As, Ks)]
    anchors = np.concatenate(anchors, axis=0)

    # Transpose and reshape predicted bbox transformations to get them
    # into the same order as the anchors:
    #
    # bbox deltas will be (1, 4 * A(x), H, W) format
    # transpose to (1, H, W, 4 * A(x))
    # reshape to (1 * H * W * A(x), 4) where rows are ordered by (h, w, a)
    # in slowest to fastest order

    #bbox_deltas = bbox_deltas.reshape((-1, 4)) #(HxWxA, 4)

    bbox_deltas = [bbox_delta.reshape((-1, 4)) for bbox_delta in bbox_deltas]
    bbox_deltas = np.concatenate(bbox_deltas, axis=0)

    # Convert anchors into proposals via bbox transformations
    proposals = bbox_transform_inv(anchors, bbox_deltas)

    # 2. clip predicted boxes to image
    proposals = clip_boxes(proposals, im_info[:2])

    # 3. remove predicted boxes with either height or width < threshold
    # (NOTE: convert min_size to input image scale stored in im_info[2])
    keep = _filter_boxes(proposals, min_size * im_info[2])
    proposals = proposals[keep, :]
    scores = scores[keep]

    # 4. sort all (proposal, score) pairs by score from highest to lowest
    # 5. take top pre_nms_topN (e.g. 6000)
    order = scores.ravel().argsort()[::-1]
    if pre_nms_topN > 0:
        order = order[:pre_nms_topN]
    proposals = proposals[order, :]
    scores = scores[order]

    # 6. apply nms (e.g. threshold = 0.7)
    # 7. take after_nms_topN (e.g. 300)
    # 8. return the top proposals (-> RoIs top)
    keep = nms(np.hstack((proposals, scores)), nms_thresh)
    if post_nms_topN > 0:
        keep = keep[:post_nms_topN]
    proposals = proposals[keep, :]
    scores = scores[keep]
    # Output rois blob
    # Our RPN implementation only supports a single input image, so all
    # batch inds are 0
    batch_inds = np.zeros((proposals.shape[0], 1), dtype=np.float32)
    blob = np.hstack((batch_inds, proposals.astype(np.float32, copy=False)))

    rpn_rois = blob

    if cfg_key == 'TEST':
        # assign rois to level Pk    (P2 ~ P6)
        def calc_level(width, height):
            return min(6, max(2, int(4 + np.log2(np.sqrt(width * height) / 224))))

        level = lambda roi : calc_level(roi[3] - roi[1], roi[4] - roi[2])   # roi: [0, x0, y0, x1, y1]

        leveled_rois = [None] * 5
        leveled_idxs = [[], [], [], [], []]
        for idx, roi in enumerate(rpn_rois):
            level_idx = level(roi) - 2
            leveled_idxs[level_idx].append(idx)

        for level_idx in xrange(0, 5):
            leveled_rois[level_idx] = rpn_rois[leveled_idxs[level_idx]]

        rpn_rois = np.concatenate(leveled_rois, axis=0)

        return leveled_rois[0], leveled_rois[1], leveled_rois[2], leveled_rois[3], leveled_rois[4], rpn_rois

    return rpn_rois
    #top[0].reshape(*(blob.shape))
    #top[0].data[...] = blob

    # [Optional] output scores blob
    #if len(top) > 1:
    #    top[1].reshape(*(scores.shape))
    #    top[1].data[...] = scores

def _filter_boxes(boxes, min_size):
    """Remove all boxes with any side smaller than min_size."""
    ws = boxes[:, 2] - boxes[:, 0] + 1
    hs = boxes[:, 3] - boxes[:, 1] + 1
    keep = np.where((ws >= min_size) & (hs >= min_size))[0]
    return keep
