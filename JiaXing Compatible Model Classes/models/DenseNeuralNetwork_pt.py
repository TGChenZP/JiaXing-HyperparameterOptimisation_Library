import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np

from torch.utils.data import Dataset, DataLoader





class CustomDataset(Dataset):
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __len__(self):
        return len(self.x)

    def __getitem__(self, idx):
        x = torch.tensor(self.x.iloc[idx].values, dtype=torch.float32)
        y = torch.tensor(self.y.iloc[idx], dtype=torch.float32)
        return x, y
    




class DenseNeuralNetwork(nn.Module):
    def __init__(self, 
            n_hidden_layers, 
            hidden_layer_n_neurons, 
            activation_function, 
            dropout_prob, 
            input_size, 
            output_size, 
            batch_normalisation,
            last_activation_function = 'relu',):

        super(DenseNeuralNetwork, self).__init__()

        self.n_hidden_layers = n_hidden_layers
        self.batch_normalisation = batch_normalisation

        self.ACTIVATION_FUNCTIONS_MAP = {'relu': nn.ReLU(), 
                                        'sigmoid': nn.Sigmoid(), 
                                        'tanh': nn.Tanh(), 
                                        'softmax': nn.Softmax(dim=1)}

        # Define layers
        self.nn_layers = nn.ModuleList([nn.Linear(input_size, hidden_layer_n_neurons[0])])
        if self.batch_normalisation:  
            self.batch_norm_layers = nn.ModuleList([])
        self.activation_layer = nn.ModuleList([self.ACTIVATION_FUNCTIONS_MAP[activation_function]])
        self.dropout_layer = nn.ModuleList([nn.Dropout(dropout_prob)])
        
        for i in range(n_hidden_layers-1):
            self.nn_layers.append(nn.Linear(hidden_layer_n_neurons[i], hidden_layer_n_neurons[i+1]))
            self.batch_norm_layers.append(nn.BatchNorm1d(hidden_layer_n_neurons[i + 1]))
            self.activation_layer.append(self.ACTIVATION_FUNCTIONS_MAP[activation_function])
            self.dropout_layer.append(nn.Dropout(dropout_prob))

        self.nn_layers.append(nn.Linear(hidden_layer_n_neurons[-1], output_size))
        self.activation_layer.append(self.ACTIVATION_FUNCTIONS_MAP[last_activation_function])


    def forward(self, x, training=True):
        out = self.nn_layers[0](x)

        for i in range(self.n_hidden_layers):
            if i != 0:
                out = self.nn_layers[i](out)
            
            if self.batch_normalisation:
                if i != 0:  # Exclude batch normalization for the input layer
                    out = self.batch_norm_layers[i - 1](out)

            out = self.activation_layer[i](out)

            if training:
                out = self.dropout_layer[i](out)
            
        out = self.nn_layers[-1](out)
        out = self.activation_layer[-1](out)
        
        return out
    




class DNN_const_pt:
    
    def __init__(self, 
                 n_hidden_layers, 
                 activation, 
                 lambda_lasso, 
                 epoch_batch_size, 
                 batch_size,
                 learning_rate, 
                 num_epochs, 
                 random_state, 
                 dropout_prob,
                 hidden_layer_n_neuron,
                 batch_normalisation = False,
                 verbose = False,
                 gpu = False,
                 gpu_id = 0,
                 loss_function='MSE',
                 last_activation_function = 'relu',
                 **kwargs):

        self.n_hidden_layers = n_hidden_layers
        self.activation = activation
        self.lambda_lasso = lambda_lasso
        self.learning_rate = learning_rate
        self.num_epochs = num_epochs
        self.epoch_batch_size = epoch_batch_size
        self.batch_size = batch_size
        self.random_state = random_state
        self.hidden_layer_n_neuron = hidden_layer_n_neuron
        self.dropout_prob = dropout_prob
        self.verbose = verbose
        self.loss_function = loss_function
        self.last_activation_function = last_activation_function
        self.batch_normalisation = batch_normalisation
        
        self.gpu = gpu
        self.gpu_id = gpu_id


        self.LOSS_FUNCTIONS_MAP = {'MSE': nn.MSELoss(), 
                                    'MAE': nn.L1Loss(), 
                                    'Huber': nn.SmoothL1Loss()}
    


    def fit(self, train_x, train_y, initial_model = None):


        self.hidden_layer_sizes = [self.hidden_layer_n_neuron for i in range(self.n_hidden_layers)]

        if type(train_y) == pd.core.frame.DataFrame:
            self.output_size = len(train_y.columns)
        else:
            self.output_size = 1
        
        self.input_size = len(train_x.columns)

       
        # Create the model
        self.model = DenseNeuralNetwork(self.n_hidden_layers, 
                                        self.hidden_layer_sizes, 
                                        self.activation, 
                                        self.dropout_prob, 
                                        self.input_size, 
                                        self.output_size,
                                        self.last_activation_function,
                                        self.batch_normalisation)

        if initial_model is not None:
            self.model.load_state_dict(initial_model.model.state_dict())        
        
        if self.gpu:
            self.model.cuda(self.gpu_id)


        # Define the loss function and optimizer
        criterion = self.LOSS_FUNCTIONS_MAP['MSE']
        optimizer = optim.Adam(self.model.parameters(), lr=self.learning_rate)

        # Create the custom datasets
        train_dataset = CustomDataset(train_x, train_y)

        self.seeds = np.random.randint(10000000, size = self.num_epochs)

        

        # Training loop
        for epoch in range(self.num_epochs):
            
            train_loader = DataLoader(train_dataset, batch_size=self.batch_size, shuffle=True, worker_init_fn=lambda _: torch.manual_seed(self.seeds[epoch]))

            instances_learnt_so_far = 0

            for batch_idx, (batch_train_x, batch_train_y) in enumerate(train_loader):
                
                if self.gpu:
                    batch_train_x, batch_train_y = batch_train_x.cuda(self.gpu_id), batch_train_y.cuda(self.gpu_id)
                # Forward pass
                outputs = self.model(batch_train_x)
                target = batch_train_y.view(-1, 1)  # Reshape target tensor to match the size of the output
                loss = criterion(outputs, target)

                # Lasso regularization
                l1_regularization = torch.tensor(0.)
                for param in self.model.parameters():
                    l1_regularization += torch.norm(param, p=1)
                loss += self.lambda_lasso * l1_regularization

                # Backward and optimize
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

                instances_learnt_so_far += self.batch_size
                
                if instances_learnt_so_far >= self.epoch_batch_size:
                    break
        
            # Print the progress
            if self.verbose:
                if (epoch + 1) % 100 == 0:
                    print(f'Epoch [{epoch+1}/{self.num_epochs}], Loss: {loss.item():.4f}')

    def predict(self, x):

        x_tensor = torch.Tensor(x.values)

        if self.gpu:
            x_tensor = x_tensor.cuda(self.gpu_id)

        with torch.no_grad():
            predictions = self.model(x_tensor, training=False)

        return predictions





class DNN_shrink_pt:
    
    def __init__(self, 
                 n_hidden_layers, 
                 activation, 
                 lambda_lasso, 
                 epoch_batch_size, 
                 batch_size,
                 learning_rate, 
                 num_epochs, 
                 random_state, 
                 dropout_prob,
                 batch_normalisation = False,
                 verbose = False,
                 gpu = False,
                 gpu_id = 0,
                 loss_function='MSE',
                 last_activation_function = 'relu',
                 **kwargs):

        self.n_hidden_layers = n_hidden_layers
        self.activation = activation
        self.lambda_lasso = lambda_lasso
        self.learning_rate = learning_rate
        self.num_epochs = num_epochs
        self.epoch_batch_size = epoch_batch_size
        self.batch_size = batch_size
        self.random_state = random_state
        self.dropout_prob = dropout_prob
        self.verbose = verbose
        self.loss_function = loss_function
        self.last_activation_function = last_activation_function
        self.batch_normalisation = batch_normalisation
        
        self.gpu = gpu
        self.gpu_id = gpu_id


        self.LOSS_FUNCTIONS_MAP = {'MSE': nn.MSELoss(), 
                                    'MAE': nn.L1Loss(), 
                                    'Huber': nn.SmoothL1Loss()}
    


    def fit(self, train_x, train_y, initial_model=None):

        if type(train_y) == pd.core.frame.DataFrame:
            self.output_size = len(train_y.columns)
        else:
            self.output_size = 1
        
        self.input_size = len(train_x.columns)

        gap = (self.input_size - self.output_size)//(self.n_hidden_layers+1)
        self.hidden_layer_sizes = [self.input_size - i * gap for i in range(self.n_hidden_layers)]
    
        # Create the model
        self.model = DenseNeuralNetwork(self.n_hidden_layers, 
                                        self.hidden_layer_sizes, 
                                        self.activation, 
                                        self.dropout_prob, 
                                        self.input_size, 
                                        self.output_size,
                                        self.last_activation_function,
                                        self.batch_normalisation)
        
        if initial_model is not None:
            self.model.load_state_dict(initial_model.model.state_dict())
        
        if self.gpu:
            self.model.cuda(self.gpu_id)


        # Define the loss function and optimizer
        criterion = self.LOSS_FUNCTIONS_MAP['MSE']
        optimizer = optim.Adam(self.model.parameters(), lr=self.learning_rate)

        # Create the custom datasets
        train_dataset = CustomDataset(train_x, train_y)

        self.seeds = np.random.randint(10000000, size = self.num_epochs)

        

        # Training loop
        for epoch in range(self.num_epochs):
            
            train_loader = DataLoader(train_dataset, batch_size=self.batch_size, shuffle=True, worker_init_fn=lambda _: torch.manual_seed(self.seeds[epoch]))

            instances_learnt_so_far = 0

            for batch_idx, (batch_train_x, batch_train_y) in enumerate(train_loader):
                
                if self.gpu:
                    batch_train_x, batch_train_y = batch_train_x.cuda(self.gpu_id), batch_train_y.cuda(self.gpu_id)
                # Forward pass
                outputs = self.model(batch_train_x)
                target = batch_train_y.view(-1, 1)  # Reshape target tensor to match the size of the output
                loss = criterion(outputs, target)

                # Lasso regularization
                l1_regularization = torch.tensor(0.)
                for param in self.model.parameters():
                    l1_regularization += torch.norm(param, p=1)
                loss += self.lambda_lasso * l1_regularization

                # Backward and optimize
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

                instances_learnt_so_far += self.batch_size
                
                if instances_learnt_so_far >= self.epoch_batch_size:
                    break
        
            # Print the progress
            if self.verbose:
                if (epoch + 1) % 100 == 0:
                    print(f'Epoch [{epoch+1}/{self.num_epochs}], Loss: {loss.item():.4f}')

    def predict(self, x):

        x_tensor = torch.Tensor(x.values)

        if self.gpu:
            x_tensor = x_tensor.cuda(self.gpu_id)

        with torch.no_grad():
            predictions = self.model(x_tensor, training=False)

        return predictions