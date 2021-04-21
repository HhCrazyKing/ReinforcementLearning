from __future__ import absolute_import

from numpy import asarray, power as pow

from LeastSquareLoss import LeastSquareLoss
import logging

logging.basicConfig(level=logging.INFO,
                    format='%(levelname)s -  %(asctime)s - %(filename)s -  %(name)s - %(funcName)s - %(message)s')
logger = logging.getLogger(__name__)


class BaseTree(object):
    """
    BaseTree
    =========
    Base model in xgboost with tree form.
    it is similar to cart regressor except gain formula.
    ---------------------------------

    Attribute:
    ===============
        1. max_depth: int, default=5
            Maximum depth of the tree
        2. min_samples: int, default=5
            The minimum number of samples in the leaf nodes of the tree.
        3. split_threshold: float, default=10
            The current point is split when the gain value of the optimal segmentation point is less than this value.
        4. gamma: int or float, default=1
            Parameter used to compute the best value of loss function in a iteration
        5. Lambda: int or float, default=1
            Parameter used to select the best split feature and value and best value of loss function in a iteration.
        6. loss_func: function, default=LeastSquareLoss
            The function to calculate g and h in xgboost.
    Method:
    ========
    1. train(self, X, y, depth=1):
        The method for training base model with tree form in xgboost.
    2. select_best_split(self, X, y):
        select the best feature and value of it in passed X and y.
    3. split_dataset(self, X, y, split_feature, split_value)
            using the feature and value passed to split the dataset.
    4. single_predict(self, x, tree=None)
        predict the label of single sample.
        the default value of tree is trained tree ahead.
    5. predict(self, X)
        Predict the labels of multiple samples at once.
    6. score(self, X, y)
        Evaluate the quality of the base model
    ------------------------------------------------
    Note:
         the X in above method must contains two columns named g and h in xgboost.
    """

    def __init__(self,
                 max_depth=5,
                 min_samples_split=5,
                 split_threshold=10,
                 gamma=1,
                 Lambda=1,
                 loss_func=LeastSquareLoss):
        self.max_depth = max_depth
        self.min_samples_split = min_samples_split
        self.split_threshold = split_threshold
        self.gamma = gamma
        self.Lambda = Lambda
        self.loss_func = loss_func

    def train(self, X, y, depth=1):
        """
        fit(self, X, y)
        ===============
        Train base trees by recursive method.
        -----------------
        Parameters:
            X: dataframe
                Current feature matrix.
            y: array_like
                Current corresponding label.
        """
        # if depth == 1, we need to initialize feature_names at once
        if depth == 1:
            # get the feature name of feature
            self.feature_names = X.columns[:-2]

        # initialize G and H
        self.G = X["g"].sum()
        self.H = X["h"].sum()

        # if depth is bigger to max_depth u initialized.return the value writen in this xgboost paper.
        if depth > self.max_depth:
            logger.info("The depth of the tree reaches max_depth({}).".format(self.max_depth))
            self.tree = -self.G / (self.H + self.Lambda)
            return self.tree

        # if the numbers of samples in X less than min_samples
        # return the mean value of corresponding labels.
        if X.shape[0] < self.min_samples_split:
            logger.info("The number of samples in X less than min_samples_split({} < {}).".format(X.shape[0],
                                                                                                  self.min_samples_split))
            self.tree = -self.G / (self.H + self.Lambda)
            return self.tree

        # get the best split point
        best_feature, best_value, gain = self.select_best_split(X)

        # if loss reduction less than split_threshold, return the mean value.
        if gain < self.split_threshold:
            logger.info("the value of gain is {}, less than split_threshold({})".format(gain, self.split_threshold))
            self.tree = -self.G / (self.H + self.Lambda)
            return self.tree

        # print logging
        logger.info("best_feature:{}, best_value:{}, gain:{}".format(best_feature, best_value, gain))
        loss_reduction = (1 / 2) * gain - self.gamma
        logger.info("The loss reduction after the split is {}".format(loss_reduction))
        # split current dataset by best_feature and best_value above
        left, right = self.split_dataset(X, y, best_feature, best_value)

        # generate the root of tree
        # @denote that u can't revise following tree to self.tree,it will cause Recursion cannot be performed.
        tree = {best_feature: {}}
        # Recursive building tree
        tree[best_feature][str(best_value) + "(l)"] = self.train(*left, depth=depth + 1)
        tree[best_feature][str(best_value) + "(r)"] = self.train(*right, depth=depth + 1)

        self.tree = tree

        return tree

    def select_best_split(self, X):
        """
        This method is to select the best feature under some criterion(here is gain value).
        ===============================
        Parameters:
            1. X : dataframe
                feature matrix of dataset.
        """
        # gain_ls is used to store the gain value corresponding to each split point.
        gain_ls = []
        # Traverse all the features and values that can be used to split the dataset
        # we call it candidate feature and candidate value
        for candidate_feature in self.feature_names:
            # set G_l = 0 and H_l = 0
            G_l, H_l = 0, 0
            # iterate candidate value of candidate feature
            for candidate_value in X[candidate_feature].drop_duplicates().sort_values(ascending=True):
                G_l += X[X[candidate_feature] == candidate_value]["g"].sum()
                H_l += X[X[candidate_feature] == candidate_value]["h"].sum()
                G_r, H_r = self.G - G_l, self.H - H_l
                # Prevent division by zero
                if -self.Lambda not in (H_l, H_r, self.H):
                    gain = (pow(G_l, 2) / (H_l + self.Lambda)) + (pow(G_r, 2) / (H_r + self.Lambda)) - (pow(self.G, 2) / (self.H + self.Lambda))
                    gain_ls.append((candidate_feature, candidate_value, gain))

        # get the best feature and value from above gini_ls using compare the 3th element to find minimal variance
        best_index = 0
        for i in range(len(gain_ls)):
            if gain_ls[i][2] > gain_ls[best_index][2]:
                best_index = i
        return gain_ls[best_index]

    def split_dataset(self, X, y, split_feature, split_value):
        """
        split the dataset passed by the split_feature and split_value
        in this method.
        --------------------------------------
        Parameters:
            1. X : dataframe
                feature matrix of dataset.
            2. y : ndarray
                label vector of dataset.
            3. split_feature: str
                name of feature using split the dataset.
            4. split_value: str or float or int
                value of split feature using split the dataset passed.
        """
        # get index of row satisfy the condition, denoted as group_index
        group_index = X[split_feature] > split_value
        return (X[~group_index], y[~group_index]), (X[group_index], y[group_index])

    def single_predict(self, x, tree=None):
        """
            This method can predict a single sample's label.
        """
        # If tree == None, set it as self.tree
        if tree is None:
            tree = self.tree
        # if tree is a number, it is the output we expect
        if isinstance(tree, float):
            return tree
        # get the feature name in the first layer
        feature_name = list(tree.keys())[0]
        # get left/right sub tree
        left, right = list(tree.get(feature_name).values())

        # Recursion Partition
        # get the split value through arbitrary branch
        split_value = list(tree.get(feature_name).keys())[0].split('(')[0]
        if x[feature_name] > float(split_value):
            return self.single_predict(x, right)
        else:
            return self.single_predict(x, left)

    def predict(self, X):
        """
        predict labels of multiple samples
        """
        res = []
        for i in range(X.shape[0]):
            res.append(self.single_predict(X.iloc[i]))

        return asarray(res)

    def score(self, X, y):
        y_pred = self.predict(X)
        return pow(y_pred - y, 2).mean()